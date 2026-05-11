---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Resume Recovery State Contract for Abnormal PR States UAT Recovery and Split

## 1. Context & Problem (业务背景与核心痛点)
当前 `leio-sdlc` 的 `resume` 仍然带有明显的“继续当前 PR / 扫一遍现有 artifacts 然后猜下一步”的历史倾向，而不是基于一个**最小、明确、authoritative 的恢复状态契约**来恢复执行。这在真实运行中已经暴露出三类高度相关的问题：

1. **abnormal PR state 会被错误跳过，甚至被当成 queue complete**
   - 当前 `resume` 似乎只会重新打开 `status: in_progress` 的 PR；
   - 对 `blocked_fatal` 这类非成功终止状态，没有清晰恢复语义；
   - 结果就是：fatal PR 没被视为待处理工作，队列被误判为空，run 甚至可能直接跳到 UAT；
   - 这意味着 `blocked_fatal` / 非成功状态并没有被当作“未完成执行路径”，而是被错误地从恢复路径中排除。

2. **中断后的 UAT miss automatic handling chain 无法 deterministic 地接回**
   - `leio-sdlc` 已经有 UAT miss 自动处理链；
   - 但如果该链在中途被打断，当前 resume 逻辑无法可靠识别“当前 run 其实已经处于 UAT recovery path”；
   - 恢复时可能退化成普通 current-PR resume，从而丢失真正的恢复上下文。

3. **`resume --split` 缺乏 authoritative current-state 约束**
   - 如果当前 run 的 active PR 与当前恢复状态没有被显式持久化，那么 `resume --split` 的 split 对象本身就可能不可靠；
   - 对 abnormal PR states、replacement PR 路径、以及 UAT recovery 中断场景尤其如此。

这些问题的共同根因不是“resume 有若干 if 写错了”，而是：

> **系统缺少一个单项目单活（single active SDLC per project）前提下的 authoritative persisted recovery state contract。**

当前现场里虽然已经有很多 artifacts：
- `baseline_commit.txt`
- `run_manifest.json`
- PR frontmatter `status`
- `uat_report.json`
- review/verifier artifacts
- git branch / workspace 状态

但这些 artifacts 的职责并不统一。resume 现在更像是在做 forensic guessing，而不是在读取一个 authoritative current-state contract。

本 PRD 的目标不是重写整个 orchestrator，也不是把恢复系统升级成多 run 并发仲裁平台，而是基于**单项目同一时刻只会有一个 SDLC run 活跃**这一明确前提，补齐一个窄边界、可审计、可唯一实现的恢复协议，使系统可以：

- 正确识别 abnormal PR states 不是 queue complete；
- 为 `blocked_fatal` / 非成功 PR states 定义明确的 resume 语义；
- 在 interrupted UAT recovery 场景中 deterministic 地 reconnect；
- 让 `resume --split` 依附于 authoritative active current PR；
- 在状态缺失、冲突或不一致时 fail closed / HITL，而不是静默猜测继续。

本 PRD **不处理**：
- 同项目多个 SDLC run 并发运行的 arbitration / ownership 设计；
- dirty branch / dirty workspace archive 策略的完整治理（这更接近 #15）；
- Gemini provider continuity / session discovery guard 的全面重构；
- 全量 orchestrator FSM rewrite；
- recovery observability / TTL telemetry 工程。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须冻结 single-active-run assumption**
   - 本 PRD 的恢复语义建立在以下前提上：
     - 同一个项目同一时刻只会有一个 active SDLC run；
   - 实现不得为同项目多 run 并发协调设计复杂 arbitration 逻辑。

2. **必须引入固定路径的 authoritative persisted recovery state artifact**
   - 每个 run 必须在以下固定路径持久化当前恢复状态 artifact：
```text
<run_dir>/resume_state.json
```
   - `resume` 必须把该文件作为首要 current-state source；
   - 不得继续以 PR frontmatter / scattered files / queue scanning 作为新的首要状态来源。

3. **必须冻结 `resume_state.json` 的最小 required schema**
   - `resume_state.json` 必须至少包含以下 required keys：
```text
state
currentPrPath
currentBranch
baselineCommit
recoveryMode
splitAllowed
updatedAt
```
   - 字段类型必须固定为：
     - `state`: string enum
     - `currentPrPath`: string or null
     - `currentBranch`: string or null
     - `baselineCommit`: string
     - `recoveryMode`: string enum
     - `splitAllowed`: boolean
     - `updatedAt`: ISO-8601 string

4. **abnormal PR state 不是 queue complete**
   - 非成功 PR states（至少包括 `blocked_fatal`，以及其他明确非成功状态）不得因为“不属于 `open` / `in_progress`”就被视为队列完成；
   - `closed` 仅能被视为 terminal-success；
   - `superseded` / `blocked_fatal` / 其他 abnormal states 的 resume 语义必须明确，而不是被隐式忽略。

5. **必须冻结 `blocked_fatal` / 非成功 PR state 的恢复语义**
   - 对 abnormal PR states，必须区分“状态本身明确”与“状态解析有歧义”两类情况；
   - 当 authoritative `resume_state.json` 明确表明当前 active PR 处于 `blocked_fatal` 时，`resume` **必须直接将其重新纳入恢复路径**，不得把它当成 queue complete，也不得把它当作可选分支；
   - 只有在 current PR / current recovery stage / state mapping 本身不明确、缺失、损坏或冲突时，系统才允许 fail closed 并进入 manager/HITL blocker；
   - 不允许在 `blocked_fatal` 已明确的前提下继续犹豫、跳过、或直接进入下游阶段（尤其是 UAT）。

6. **必须支持 interrupted UAT recovery chain reconnect**
   - 如果 run 在中断前已进入既有 UAT miss automatic handling chain，`resume` 必须依据 authoritative persisted state 接回该链；
   - 不允许把这种场景静默降级成 generic ordinary resume。

7. **`resume --split` 必须建立在 authoritative active PR state 之上**
   - 只有当 `resume_state.json` 明确指出当前 active PR 且当前 state 允许 split 时，`resume --split` 才可执行；
   - split 目标不能靠“猜当前 PR”得到。

8. **必须冻结最小恢复状态枚举与 recoveryMode 枚举**
   - `resume_state.json.state` 允许值必须固定为：
```text
PLANNER_ACTIVE
CODER_ACTIVE
REVIEWER_ACTIVE
VERIFIER_ACTIVE
UAT_RECOVERY_ACTIVE
COMPLETED_PASS
WITHDRAWN
BLOCKED
```
   - `resume_state.json.recoveryMode` 允许值必须固定为：
```text
mainline
uat_recovery
split
```
   - `splitAllowed` 必须是显式布尔值，不允许由 coder 通过状态外推去猜测。

9. **必须冻结 conflict-precedence rules**
   - `resume` 读取状态时，优先级必须固定为：
     1. `<run_dir>/resume_state.json`
     2. `run_manifest.json` / `baseline_commit.txt`
     3. PR frontmatter `status`
     4. `uat_report.json` / 其他 role artifacts
     5. git branch / workspace 现场
   - 当 1 与 2-5 冲突时，系统不得静默猜测继续；
   - 必须 fail closed 或进入明确的 manager/HITL blocker。

10. **必须冻结 mandatory persistence checkpoints / transition moments**
   - orchestrator 必须至少在以下节点写入或更新 `<run_dir>/resume_state.json`：
     1. planner spawn 之前：写入 `PLANNER_ACTIVE`
     2. current PR 被选为 active 并进入 coder 之前：写入 `CODER_ACTIVE` 与 `currentPrPath/currentBranch`
     3. 进入 reviewer 之前：写入 `REVIEWER_ACTIVE`
     4. 进入 verifier/UAT 之前：写入 `VERIFIER_ACTIVE`
     5. 进入 UAT miss automatic handling chain 时：写入 `UAT_RECOVERY_ACTIVE` 且 `recoveryMode=uat_recovery`
     6. `resume --split` supersede 原 PR 并切回 planner continuation path 时：写入 `recoveryMode=split` 以及新的 active PR context
     7. run 成功完成时：写入 `COMPLETED_PASS`
     8. run 被 withdraw 时：写入 `WITHDRAWN`
     9. run 被保护性阻塞时：写入 `BLOCKED`
   - 不允许不同实现各自决定何时落盘这些关键状态边界。

11. **状态缺失 / 冲突 / 歧义时必须 fail closed / HITL**
   - 如果 `resume_state.json` 缺失、损坏、与现场冲突、或不足以无歧义恢复：
     - `resume` 必须 fail closed；
     - 或进入显式 manager/HITL 路径；
   - 不得继续静默猜测。

### Non-Functional Requirements

1. **本 PRD 必须保持窄边界**
   - 只围绕 #24、#16 与 `resume --split` 的最小恢复状态契约；
   - 不扩张为 dirty-state 归档系统全量重构；
   - 不扩张为多 run 并发恢复系统。

2. **恢复逻辑必须优先 correctness / auditability**
   - 在“尽量继续跑”与“状态可审计/可解释”之间，优先选择后者。

3. **恢复状态语义必须 deterministic**
   - 不能继续依赖隐式 heuristics；
   - 必须能从固定协议与现场校验中得出稳定结论。

### User Stories

- **As an operator**, I want `resume` to stop treating abnormal PR states as if the queue were complete, so fatal PRs are not silently skipped.
- **As an operator**, I want interrupted UAT recovery to reconnect to the existing automatic handling chain, so the most important recovery path stays deterministic after interruption.
- **As an operator**, I want `resume --split` to act on a clearly identified current PR, so split decisions are grounded in authoritative state rather than guesses.
- **As a maintainer**, I want state ambiguity to fail closed or escalate to HITL, so resume no longer fabricates progress by inference.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **single-active-run resume recovery state contract** 路线：
- 不做多 run 设计；
- 不做全量 FSM rewrite；
- 只为当前单 run 的 resume 语义补一套最小显式恢复状态契约。

### 3.1 Core design principle
`resume` 的职责必须从：
- “看看当前 queue 里还有没有 `in_progress` PR / 有没有散落 artifact”

转成：
- “先读取 `<run_dir>/resume_state.json` 作为 authoritative current-state source”
- “再根据该 state 和现场一致性决定恢复分支”

### 3.2 Authoritative recovery state contract
系统必须在当前 run 目录中维护一个固定路径的 authoritative current-state artifact：
```text
<run_dir>/resume_state.json
```

该 contract 的固定 required keys 为：
```text
state
currentPrPath
currentBranch
baselineCommit
recoveryMode
splitAllowed
updatedAt
```

字段约束：
- `state`: string enum
- `currentPrPath`: string|null
- `currentBranch`: string|null
- `baselineCommit`: string
- `recoveryMode`: `mainline|uat_recovery|split`
- `splitAllowed`: boolean
- `updatedAt`: ISO-8601 string

该 artifact 是 `resume` 的首要状态来源，而不是实现可自由命名/自由扩缩的建议性数据结构。

### 3.3 Existing artifacts reclassified by responsibility
本 PRD 明确：
- `run_manifest.json`：run identity / anchor，不是 mutable current-state source
- `baseline_commit.txt`：baseline anchor，不是 current-state source
- PR frontmatter `status`：PR queue lifecycle 的输入，但不是全局恢复状态的唯一真相
- `uat_report.json`：UAT/verifier payload，不足以单独表达“当前正处于 UAT recovery path”
- git branch / workspace 状态：现场校验输入，不是 orchestration current-state source

### 3.4 Minimum recoverable state set
本次最小恢复状态集合必须固定为：
- `PLANNER_ACTIVE`
- `CODER_ACTIVE`
- `REVIEWER_ACTIVE`
- `VERIFIER_ACTIVE`
- `UAT_RECOVERY_ACTIVE`
- `COMPLETED_PASS`
- `WITHDRAWN`
- `BLOCKED`

这些值必须作为 `resume_state.json.state` 的固定 enum 使用；
不得由不同实现自行改名、合并或临时扩写后再靠解释层兼容。

### 3.5 Abnormal PR state semantics
#### A. Terminal-success
- `closed`

#### B. Non-success / abnormal states
至少包括：
- `blocked_fatal`
- 以及其他明确非成功状态

这些状态不得因为“不属于 `open` / `in_progress`”而被等同于 queue complete。

其中：
- `blocked_fatal` 在 authoritative `resume_state.json` 已明确 `currentPrPath` 与当前恢复上下文的前提下，**必须直接恢复**；
- 它不是可选恢复分支，也不是需要再次人工判断的模糊状态；
- 只有当 `resume_state.json` 缺失、损坏、或与 validating artifacts 冲突而无法确认当前 active PR 时，系统才允许 fail closed / HITL。

#### C. Replaced path
- `superseded` 不能自动等同于成功；
- 其语义必须和当前 `resume_state.json` 一起解释，尤其在 replacement PR path 存在时。

### 3.6 Interrupted UAT recovery reconnect
当 `<run_dir>/resume_state.json` 表明 run 已进入 UAT miss automatic handling chain，且至少包含：
```text
state = UAT_RECOVERY_ACTIVE
recoveryMode = uat_recovery
```
时：
- `resume` 必须直接进入 UAT recovery reconnect 分支；
- 不允许退化成 generic current-PR resume；
- 不允许因为 queue 扫描结果“看起来没有 active PR”就跳到 UAT success / ordinary downstream path。

### 3.7 `resume --split`
`resume --split` 必须满足：
1. `<run_dir>/resume_state.json` 明确表明存在 active current PR
2. `resume_state.json.state` 属于允许 split 的状态类
3. `resume_state.json.splitAllowed == true`

split 之后：
- 原 PR 被标记为 `superseded`（或等价 replaced semantics）
- `resume_state.json` 被更新为 planner continuation 所需的新当前状态
- `recoveryMode` 切换为：
```text
split
```
- 新 slices 进入后续队列

本次优先复用现有 planner slicing 能力，不重新设计独立 planner protocol。

### 3.8 Conflict precedence and ambiguity handling
`resume` 读取状态时，优先级必须固定为：
1. `<run_dir>/resume_state.json`
2. `run_manifest.json` / `baseline_commit.txt`
3. PR frontmatter `status`
4. `uat_report.json` / review / verifier artifacts
5. git branch / workspace 现场

规则：
- 当 1 存在且与 2-5 一致时，直接按 1 恢复；
- 当 1 与 2-5 冲突时，系统不得静默猜测；
- 必须 fail closed 或进入显式 manager/HITL 路径；
- 当 1 缺失时，不允许把 scattered artifacts 重新提升为新的 primary truth。

### 3.9 Mandatory persistence checkpoints
orchestrator 必须至少在以下节点写入或更新 `<run_dir>/resume_state.json`：
1. planner spawn 之前：写入 `PLANNER_ACTIVE`
2. current PR 被选为 active 并进入 coder 之前：写入 `CODER_ACTIVE` 与 `currentPrPath/currentBranch`
3. 进入 reviewer 之前：写入 `REVIEWER_ACTIVE`
4. 进入 verifier/UAT 之前：写入 `VERIFIER_ACTIVE`
5. 进入 UAT miss automatic handling chain 时：写入 `UAT_RECOVERY_ACTIVE` 且 `recoveryMode=uat_recovery`
6. `resume --split` supersede 原 PR 并切回 planner continuation path 时：写入 `recoveryMode=split` 以及新的 active PR context
7. run 成功完成时：写入 `COMPLETED_PASS`
8. run 被 withdraw 时：写入 `WITHDRAWN`
9. run 被保护性阻塞时：写入 `BLOCKED`

### 3.10 Single-active-run simplification
本 PRD 明确利用以下前提来简化设计：
- 同一项目同一时刻只有一个 SDLC run 活跃

因此，本次实现不需要设计：
- 多 run ownership arbitration
- 多 run current-PR 冲突解决
- 并发 run recovery-state 选主协议

这也是本次 PRD 比旧版恢复 PRD 更小、更可执行的关键前提。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: `blocked_fatal` PRs are not treated as queue complete and are resumed directly when state is clear**
  - **Given** `<run_dir>/resume_state.json` clearly identifies the current active PR and marks the run context such that the current active PR is in `blocked_fatal`
  - **When** `resume` is invoked
  - **Then** the run is not treated as queue-complete merely because no PR remains in `open` / `in_progress`
  - **And** the `blocked_fatal` PR is directly re-entered into the recovery path
  - **And** the system does not skip it or jump to UAT

- **Scenario 2: abnormal PR states no longer get silently skipped before UAT**
  - **Given** a prior execution path ended abnormally rather than successfully
  - **When** `resume` evaluates the run state
  - **Then** it does not jump directly into UAT merely because ordinary queue scanning finds no `open` / `in_progress` PR

- **Scenario 3: interrupted UAT recovery reconnects to the existing UAT recovery chain**
  - **Given** a run had already entered UAT miss automatic handling before interruption
  - **And** `<run_dir>/resume_state.json` records:
```text
state = UAT_RECOVERY_ACTIVE
recoveryMode = uat_recovery
```
  - **When** `resume` is invoked after interruption
  - **Then** the run reconnects to the existing UAT recovery path
  - **And** it is not treated as a generic ordinary resume

- **Scenario 4: `resume --split` only operates on an authoritative active current PR**
  - **Given** `resume --split` is requested
  - **When** `<run_dir>/resume_state.json` does not identify a current active PR or `splitAllowed` is false or the current state does not permit split
  - **Then** the system fails closed or produces an explicit manager/HITL blocker
  - **And** it does not guess a split target

- **Scenario 5: `resume --split` can supersede the current authoritative PR when the state allows it**
  - **Given** `<run_dir>/resume_state.json` identifies a valid current active PR and a split-permitted stage
  - **When** `resume --split` is invoked
  - **Then** the current PR is superseded via the existing planner slicing path
  - **And** `resume_state.json` is updated to follow the planner-driven continuation path

- **Scenario 6: ambiguous recovery state fails closed**
  - **Given** `<run_dir>/resume_state.json` is missing, corrupt, or inconsistent with PR/frontmatter/other validating artifacts
  - **And** the system cannot unambiguously determine the current active PR or current recovery stage
  - **When** `resume` is invoked
  - **Then** the system fails closed or enters an explicit manager/HITL path
  - **And** it does not silently guess how to continue

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是某个 status 字符串判断错，而是：
- resume 继续把 scattered artifacts 当 primary truth
- abnormal PR states 仍然被误判成 done
- interrupted UAT recovery 仍然掉回 generic resume
- `resume --split` 在没有 authoritative current PR 的前提下盲目操作

### 推荐测试策略

1. **优先做 deterministic orchestrator recovery tests**
   - 用 synthetic run_dir / PR files / `resume_state.json` / related artifacts 构造恢复场景；
   - 避免依赖 live LLM。

2. **必须覆盖 abnormal PR state vs queue complete 回归**
   - 特别是 `blocked_fatal` 被跳过的情况；
   - 以及 `superseded` / replacement path 的最小正确性验证。

3. **必须覆盖 interrupted UAT recovery reconnect**
   - 构造已进入 UAT recovery path 的中断现场；
   - 验证 resume 接回原链路，而不是普通 resume。

4. **必须覆盖 `resume --split` 的正反两面**
   - 有 authoritative active PR 时可 split；
   - 无 active PR / stage 不允许时 fail closed。

5. **必须覆盖 ambiguity fail-closed**
   - 缺失 state
   - 冲突 state
   - state 与 PR/frontmatter/现场不一致

### Quality Goal
修复完成后，`resume` 必须满足：
- abnormal PR states 不再被错误视为 queue complete；
- interrupted UAT recovery 能 deterministic reconnect；
- `resume --split` 依附于 authoritative active PR；
- 状态歧义时 fail closed / HITL，而不是猜测继续。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- 承载 `<run_dir>/resume_state.json` 协议实现的最小辅助模块（如实现确有必要）
- `scripts/structured_state_parser.py`（如需要扩展 PR status parsing / interpretation）
- `scripts/spawn_planner.py`（仅在 `resume --split` 接线确有必要时）
- 与 resume / UAT recovery / split 相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 基于旧版 `PRD_SDLC_Resume_State_Recovery_and_Control_Quick_Fixes.md` 提炼出更窄的新执行稿，只保留 #24、#16 与 `resume --split` 的核心恢复状态契约问题。
- **Design simplification**: 明确采用“单项目单活 SDLC run”前提，放弃为多并发 run 设计恢复协议，从而显著简化 current-state / current-PR / split 语义。
- **v2.0 Revision Rationale**: 基于 auditor 反馈，将恢复状态协议升级为字节级确定：冻结 `<run_dir>/resume_state.json` 路径、required keys、enum values、precedence rules 与 mandatory persistence checkpoints。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`recovery_state_file_name`**:
```text
resume_state.json
```

- **`terminal_success_pr_status`**:
```text
closed
```

- **`non_success_pr_status_example`**:
```text
blocked_fatal
```

- **`recovery_state_enum_values`**:
```text
PLANNER_ACTIVE
CODER_ACTIVE
REVIEWER_ACTIVE
VERIFIER_ACTIVE
UAT_RECOVERY_ACTIVE
COMPLETED_PASS
WITHDRAWN
BLOCKED
```

- **`recovery_mode_enum_values`**:
```text
mainline
uat_recovery
split
```

- **`recovery_state_required_keys`**:
```text
state
currentPrPath
currentBranch
baselineCommit
recoveryMode
splitAllowed
updatedAt
```

- **`recovery_state_key_for_uat_chain`**:
```text
UAT_RECOVERY_ACTIVE
```

- **`split_flag`**:
```text
--split
```
