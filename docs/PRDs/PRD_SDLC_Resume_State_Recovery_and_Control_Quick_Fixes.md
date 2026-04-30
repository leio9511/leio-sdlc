---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: SDLC Resume Recovery State Contract and Control Quick Fixes

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前的 `resume` 能力仍然带有“继续当前 PR”的历史实现倾向，而不是真正基于**显式恢复状态契约**来恢复状态机执行。这在真实运行里暴露出了三个彼此耦合的问题域：

1. **恢复状态没有 authoritative persisted contract**
   - 当前运行现场中已经存在多种 artifacts，例如：`baseline_commit.txt`、`run_manifest.json`、PR frontmatter `status`、`uat_report.json`、workspace `STATE.md`、git branch / worktree 状态。
   - 但这些 artifacts 的职责并不统一：有的是基线锚点，有的是队列状态，有的是 verifier payload，有的是阻塞提示，有的是运行时现场。
   - 当 `resume` 试图从这些 scattered artifacts 中“推断”当前状态时，本质上是在做 forensic guessing，而不是从 authoritative recovery contract 恢复。

2. **没有显式恢复状态时，dirty resume 与 UAT miss recovery resume 都不可信**
   - 在 dirty branch、dirty workspace、残缺 worktree、半完成恢复现场上直接 resume，会把旧状态继续带入新执行，破坏 correctness 与可审计性。
   - `leio-sdlc` 已有 UAT miss 自动处理流程，但如果流程在中途被打断，当前系统没有一套显式持久化状态来表明 run 正处于 UAT recovery 链路，因此 resume 无法 deterministic 地接回原有链路。

3. **Gemini continuation 保护不足与 operator split 入口不足，都是恢复状态契约缺失的下游问题**
   - `ISSUE-1209` 已确认：`gemini --list-sessions -o json` 并不会返回可直接 `json.loads()` 的 JSON，因此不能把 Gemini provider-native session mapping 当成可靠恢复依据。
   - `ISSUE-1210` 提出的 `resume --split` 也必须建立在“当前 active PR 与当前恢复状态是明确已知的”前提上，否则 split 的对象本身就不可靠。

因此，本 PRD 的核心目标不是重写整个 orchestrator，也不是重定义 UAT miss 业务流程，而是：

> **为 `resume` 补齐一个最小显式恢复状态契约（Resume Recovery State Contract），让恢复入口先依赖 authoritative persisted state，再在其上实现 dirty-state guard、Gemini continuity guardrail 与 operator-controlled split。**

本 PRD 统一处理以下三个 issue：
- `ISSUE-1199`: SDLC Resume逻辑缺陷：在脏branch上直接恢复，应封存后从干净master重试当前PR（含 UAT miss 自动处理链中断后的恢复问题）
- `ISSUE-1209`: Gemini CLI --list-sessions does not return JSON, breaking SDLC session mapping
- `ISSUE-1210`: Support --split on resume to manually split current PR

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. 系统必须为每个 run 持久化一个**authoritative recovery state contract**，供 `resume` 作为首要依据读取。
2. 系统必须显式定义最小可恢复状态集合，至少覆盖：
   - `PLANNER_ACTIVE`
   - `CODER_ACTIVE`
   - `REVIEWER_ACTIVE`
   - `MERGE_PENDING`
   - `VERIFIER_ACTIVE`
   - `UAT_RECOVERY_ACTIVE`
   - `COMPLETED_PASS`
   - `WITHDRAWN`
   - `BLOCKED`
3. 系统必须在进入每个 recoverable orchestration stage 之前，先写入对应的 authoritative recovery state，再启动对应子流程。
4. `resume` 必须优先读取 authoritative recovery state；现有 artifacts 只能作为校验、辅助恢复或 legacy compatibility 输入，而不能继续作为新架构下的首要状态来源。
5. 系统必须定义 recovery state 与文件/标记的明确对应关系，以及 deterministic 的状态判定规则。
6. 当 authoritative recovery state 缺失、冲突、损坏或与现场不一致时，`resume` 必须 fail closed，或进入受限/保护路径；不得静默猜测继续。
7. dirty branch / dirty workspace / inconsistent run context 下，`resume` 不得直接继续执行，必须先 archive 现场并恢复到 clean baseline 再重新进入对应状态。
8. 当 run 已进入既有 UAT miss 自动处理链且被中断时，`resume` 必须依据 authoritative recovery state 接回该既有链路，而不是降级成普通当前 PR resume。
9. Gemini runtime 不得继续假设 `gemini --list-sessions -o json` 可直接 JSON 解析；Gemini session continuity 失败时，不得伪装为 continuation success。
10. 系统必须支持 `resume --split` 作为 operator-controlled override，但仅限于 authoritative state 明确表明当前存在可 supersede 的 active PR 时。
11. `resume --split` 必须优先复用现有 planner slicing 能力（特别是 `spawn_planner.py --slice-failed-pr`），而不是重新设计独立 planner 协议。
12. 所有恢复失败、保护性拒绝、Gemini degraded behavior、split guardrail 决策都必须输出清晰、可审计的诊断结果。

### Non-Functional Requirements
1. 本次修复必须保持为 **bounded refactor**，不得演变成 orchestrator 的全量 FSM 重构。
2. 本次只为恢复语义补齐**最小显式状态机契约**，不要求一次性把所有内部细粒度重试子状态都完全显式化。
3. 本 PRD 不要求本次引入第三方 FSM framework；但 recovery state contract、state resolution rules、dispatcher 边界必须与未来内部 FSM runtime 重构兼容。
4. `ISSUE-1209` 在本 PRD 中的范围仅限于 resume / continuation 安全性所必需的 Gemini guardrail，不授权全面重构 Gemini runtime。
5. `ISSUE-1210` 在本 PRD 中必须优先复用现有 planner 切片能力，不授权重做 planner protocol。
6. 恢复逻辑必须优先保证 correctness / auditability，高于“尽量继续跑”。
7. 所有新行为必须由 deterministic 的自动化测试覆盖关键恢复分支。

### User Stories
- 作为 operator，当 SDLC 被中断时，我希望 `resume` 先读取 authoritative persisted state，而不是靠散落 artifacts 猜测当前停在哪一步。
- 作为 operator，当现场 dirty 或状态冲突时，我希望系统 fail closed 或 archive + clean restart，而不是把污染现场继续带下去。
- 作为 operator，当 run 已进入既有 UAT miss 自动处理链且中断时，我希望 `resume` 能接回这条既有链路。
- 作为 operator，当 Gemini provider-native session discovery 不可靠时，我希望系统显式降级，而不是假装 continuity 正常。
- 作为 operator，当当前 active PR 明显过大或 scope 已偏离时，我希望可以执行 `resume --split`，并确信 split 的对象是 authoritative state 明确指向的当前 PR。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### Core Design Principle
**Resume = State-Machine Resumer backed by an Authoritative Recovery State Contract**

`resume` 的职责不是“默认继续当前 PR”，而是：
1. 读取 authoritative persisted recovery state
2. 校验该状态与现场是否一致
3. 必要时 archive / reset / rebuild 恢复上下文
4. 从该状态对应的恢复分支继续执行

本 PRD 不要求一次性把 orchestrator 全量改写为宏大的 formal FSM；本 PRD 要求的是：

> **先为恢复语义补齐一套最小显式状态机契约，再在其上安全实现 resume。**

### 3.1 Authoritative Recovery State Contract
系统必须在 run_dir 中引入一个 authoritative current-state artifact，例如 `resume_state.json`，作为 `resume` 的首要状态来源。

该 contract 的职责是：
- 表达当前 run 处于哪个 recoverable orchestration state
- 记录当前 state 对应的关键上下文（如 current PR、current branch、baseline、模式）
- 为 resume 提供 deterministic 的恢复依据

同时，系统应维护一个最小 append-only transition trail（例如 `resume_journal.jsonl`），用于记录状态转换轨迹，便于法证和审计。

### 3.2 Existing Artifacts Reclassified by Responsibility
本 PRD 明确把现有 artifacts 的职责解耦如下：

1. **`run_manifest.json`**
   - 运行身份与初始锚点
   - 不是 authoritative mutable recovery state

2. **`baseline_commit.txt`**
   - clean restart / reset 的 baseline 锚点
   - 不是 orchestration current-state source

3. **PR frontmatter `status` (`open|in_progress|closed|blocked|blocked_fatal|superseded`)**
   - PR queue / slice lifecycle 语义
   - 不是全局恢复状态的唯一来源

4. **`uat_report.json`**
   - verifier / UAT payload
   - 不是独立足以声明 `UAT_RECOVERY_ACTIVE` 的 authoritative state marker

5. **workspace `STATE.md` 中的 UAT 标记（如 `UAT_ERROR` / `UAT_BLOCKED`）**
   - 人工阻塞 / 运行结果提示
   - 可作为辅助校验或 block state 证据
   - 不是新架构下的单一 authoritative recovery state

6. **git branch / worktree 状态**
   - 运行现场一致性检查输入
   - 不是 orchestration state source

### 3.3 Minimum Recoverable State Set
本次最小显式恢复状态集合为：
- `PLANNER_ACTIVE`
- `CODER_ACTIVE`
- `REVIEWER_ACTIVE`
- `MERGE_PENDING`
- `VERIFIER_ACTIVE`
- `UAT_RECOVERY_ACTIVE`
- `COMPLETED_PASS`
- `WITHDRAWN`
- `BLOCKED`

其中：
- 前 6 个为 active / recoverable orchestration states
- `COMPLETED_PASS`、`WITHDRAWN`、`BLOCKED` 为 terminal or protected states
- `CORRUPT_STATE`、`LEGACY_UNSAFE_TO_RESUME` 可作为 detector 输出结果，但不是必须持久化的正常运行状态

### 3.4 State-to-Artifact Mapping
系统必须为每个 recoverable state 明确规定“由谁写入、何时写入、哪些字段必须存在”。

最小要求如下：

1. **进入 planner 阶段前**
   - orchestrator 写入 `PLANNER_ACTIVE`
   - 记录 `baseline_commit`、`mode=mainline`、`current_pr_path=null`

2. **进入 coder 阶段前**
   - orchestrator 写入 `CODER_ACTIVE`
   - 记录 `current_pr_path`、`current_branch`、`mode=mainline`

3. **进入 reviewer 阶段前**
   - orchestrator 写入 `REVIEWER_ACTIVE`
   - 记录 `current_pr_path`、`current_branch`

4. **review 通过、merge 动作尚未完成前**
   - orchestrator 写入 `MERGE_PENDING`
   - 记录 `current_pr_path`、`current_branch`

5. **进入 verifier/UAT 阶段前**
   - orchestrator 写入 `VERIFIER_ACTIVE`
   - 记录 verifier 输入及预期输出路径（如 `uat_report.json`）

6. **进入既有 UAT miss 自动处理链前**
   - orchestrator 写入 `UAT_RECOVERY_ACTIVE`
   - 记录 `uat_report_path`、recovery mode、recovery attempt count 等关键上下文
   - 这一步是本 PRD 的关键：它必须显式持久化，而不能再依赖后验猜测

7. **run 成功完成时**
   - orchestrator 写入 `COMPLETED_PASS`

8. **run 被 withdraw 时**
   - orchestrator 写入 `WITHDRAWN`

9. **run 被 manager/hard guardrail 阻塞时**
   - orchestrator 写入 `BLOCKED`
   - 记录 blocker reason code

### 3.5 Resume State Resolution Rules
`resume` 必须采用如下优先级：

1. **Primary source**: authoritative `resume_state.json`
2. **Validation sources**: `baseline_commit.txt`、`run_manifest.json`、PR frontmatter 状态、`uat_report.json`、`STATE.md`、git 现场
3. **Decision**:
   - 如果 authoritative state 存在、合法、且与现场一致 → 进入对应 dispatcher path
   - 如果 authoritative state 存在但与现场不一致 → archive / clean restart 或 protected refusal
   - 如果 authoritative state 缺失，但属于 legacy run → 仅允许非常受限的 compatibility check；若不能无歧义恢复，则 fail closed，禁止靠 heuristics 猜状态继续
   - 如果 state 文件损坏、互斥字段同时成立、或验证结果冲突 → 输出 `CORRUPT_STATE` / protected failure

### 3.6 Dirty-State Guard
dirty-state guard 必须建立在 authoritative recovery state 之上：
- 先判定当前 state 是否可恢复
- 再校验现场是否与该 state 相容
- 如果工作树、branch、current PR branch、baseline anchor 与 state 冲突，则先 archive，再 reset / rebuild

本次优先复用现有：
- `baseline_commit.txt`
- 现有 crashed/quarantine snapshot 思路
- 现有 branch reset / checkout 逻辑

不重新设计大型法证系统。

### 3.7 Gemini Continuity Guardrail
`ISSUE-1209` 在本 PRD 中被定义为：

> **engine-level continuity 不能污染 orchestration-level recovery truth**

也就是说：
- orchestration current state 必须由 `resume_state.json` 等 authoritative contract 表达
- Gemini provider-native session mapping 仅影响“某一 stage 内是否能续接原 provider session”
- 它不能继续被当作 orchestration recovery state 的前提条件

因此本次实现要求：
1. 去掉 `gemini --list-sessions -o json` 的错误 JSON 假设
2. 如果 Gemini session discovery 不可靠，则进入显式 degraded / protected path
3. 不得把 session mapping failure 伪装成 continuity success

### 3.8 Operator-Controlled `resume --split`
`resume --split` 必须建立在 authoritative current state 之上。

本次 bounded design：
- 仅当 `resume_state.json` 明确表明存在 active current PR，且当前状态处于允许 split 的 mainline PR recoverable states（如 `CODER_ACTIVE` / `REVIEWER_ACTIVE` / `MERGE_PENDING`）时允许执行
- split 必须优先复用现有 `spawn_planner.py --slice-failed-pr`
- split 后：
  - 原 PR 标记为 `superseded`
  - authoritative recovery state 更新为 planner-driven follow-up path
  - 新 slices 进入队列

不允许在 `UAT_RECOVERY_ACTIVE`、`COMPLETED_PASS`、`WITHDRAWN`、无 active PR 等状态下盲目 split。

### Target Modules / Files
以下框架文件被明确授权纳入本次实现范围，实际改动以最小必要原则为准：
- `scripts/orchestrator.py`
- `scripts/agent_driver.py`
- `scripts/spawn_planner.py`（仅在 `--slice-failed-pr` / `--replan-uat-failures` / split 接线需要时）
- `scripts/spawn_coder.py`（如 resume dispatcher 接线确有必要）
- `scripts/spawn_reviewer.py`（如 resume dispatcher 接线确有必要）
- `scripts/spawn_verifier.py`（如 verifier/UAT recovery state 接线确有必要）
- `scripts/config.py`（仅限 Gemini continuity guardrail 需要时）
- `scripts/structured_state_parser.py`（如需复用或扩展 PR 状态解析）
- 与 resume / continuation / UAT recovery / orchestrator state 相关的测试文件
- 必要时新增小型辅助模块，如：
  - `resume_state.py`
  - `resume_dispatcher.py`
  - `resume_archive.py`

### Explicit Architectural Trade-offs
1. **Prefer explicit recovery state contract over forensic guessing**
   - 这是本次架构修正的核心。

2. **Prefer resume-oriented FSM contract over full orchestrator FSM rewrite**
   - 只定义恢复所必需的状态与转换，不在本次全量显式化所有内部子状态。

3. **Prefer existing artifacts as validation inputs, not primary truth**
   - 现有 artifacts 仍然保留价值，但不再承担 authoritative current-state source 的职责。

4. **Prefer honest degradation over fake continuity**
   - 对 Gemini engine，宁可显式降级，也不伪造 continuation 成功。

5. **Prefer future FSM compatibility without forcing current framework migration**
   - 本次不强制引入第三方 FSM framework。
   - 但 `resume_state.json`、状态枚举、状态判定规则、dispatcher 边界必须保持与未来内部 FSM runtime 重构兼容，避免将来再次推倒重来。

6. **Prefer explicit operator control over implicit automation**
   - `resume --split` 是人为 override，不要求系统自动猜何时 split。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Active orchestrator stage is durably persisted before execution enters that stage**
  - **Given** a run is about to enter planner, coder, reviewer, merge, verifier, or UAT recovery
  - **When** orchestrator transitions into that recoverable stage
  - **Then** it must first persist the authoritative recovery state for that stage before launching the downstream work

- **Scenario 2: Resume reads authoritative recovery state instead of guessing from scattered artifacts**
  - **Given** an interrupted run with a valid authoritative recovery state file
  - **When** the operator executes `resume`
  - **Then** the system must use that persisted recovery state as its primary resume source and must not infer the stage solely from leftover artifacts

- **Scenario 3: Dirty recovery context cannot continue blindly**
  - **Given** an interrupted run whose authoritative recovery state is recoverable but whose branch/worktree/context is dirty or inconsistent with the persisted state
  - **When** the operator executes `resume`
  - **Then** the system must archive the current现场, restore a clean baseline context, and only then continue from the persisted recovery state

- **Scenario 4: Existing UAT miss automatic path is resumed through explicit persisted state**
  - **Given** a run that had already entered the existing UAT miss automatic handling path and persisted `UAT_RECOVERY_ACTIVE`
  - **When** the operator executes `resume`
  - **Then** the system must reconnect to that existing UAT miss handling path rather than downgrading to a generic current-PR resume path

- **Scenario 5: Missing or ambiguous recovery state fails closed**
  - **Given** a run whose authoritative recovery state is missing, corrupted, internally inconsistent, or irreconcilable with the现场
  - **When** the operator executes `resume`
  - **Then** the system must refuse unsafe recovery or enter an explicitly protected path, rather than silently guessing and continuing

- **Scenario 6: Legacy run without new recovery contract is handled conservatively**
  - **Given** a historical run created before the new recovery state contract exists
  - **When** the operator executes `resume`
  - **Then** the system may only resume if a limited compatibility path can reconstruct the state unambiguously; otherwise it must fail closed with a clear diagnostic result

- **Scenario 7: Gemini session discovery failure does not masquerade as continuity success**
  - **Given** a Gemini-based continuation or resume path where provider-native session discovery cannot be reliably parsed
  - **When** the system attempts to restore provider continuity inside a recoverable orchestration stage
  - **Then** it must enter an explicit degraded or protected path and must not silently behave as if session mapping succeeded

- **Scenario 8: Manual split during resume only operates on an authoritative active PR**
  - **Given** an interrupted run whose authoritative recovery state identifies a valid active PR in a split-eligible mainline state
  - **When** the operator executes `resume --split`
  - **Then** the system must supersede the current PR, invoke the existing planner slicing path, and continue from the new split plan

- **Scenario 9: Invalid split states are rejected clearly**
  - **Given** a run in `UAT_RECOVERY_ACTIVE`, `COMPLETED_PASS`, `WITHDRAWN`, or with no authoritative active PR
  - **When** the operator executes `resume --split`
  - **Then** the system must reject the split request with a clear explanation

- **Scenario 10: Completed pass and withdrawn states are terminal for normal resume**
  - **Given** a run whose authoritative recovery state is `COMPLETED_PASS` or `WITHDRAWN`
  - **When** the operator executes `resume`
  - **Then** the system must not restart active execution and must return a clear terminal-state result

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risks
1. 系统虽然新增 state file，但仍然在关键恢复路径偷偷回退到 heuristics guessing
2. active state 没有在 stage 进入前持久化，导致中断后无 authoritative state 可读
3. UAT recovery 没有显式持久化 `UAT_RECOVERY_ACTIVE`，导致 resume 仍然无法接回既有链路
4. Gemini continuity 失败被错误当作 resume 失败，或者反过来被错误当作 continuity success
5. `resume --split` 在无 authoritative active PR 的情况下误触发

### Test Strategy
1. **State contract unit tests are mandatory**
   - 必须覆盖 `resume_state.json` schema、字段完整性、状态枚举合法性、冲突字段判定
   - 必须覆盖 `resume_journal.jsonl`（若实现）写入行为与顺序一致性

2. **Transition write-before-execute tests are mandatory**
   - 必须验证 orchestrator 在进入 planner / coder / reviewer / merge / verifier / UAT recovery 前，先写入对应 authoritative state

3. **Resume resolution tests are mandatory**
   - 必须覆盖：
     - valid state → correct dispatcher path
     - missing state → fail closed / protected path
     - conflicting state vs现场 → archive + clean restart or refusal
     - legacy run without new contract → conservative compatibility behavior

4. **UAT recovery continuity tests are mandatory**
   - 必须验证 `UAT_RECOVERY_ACTIVE` 被显式持久化并可在中断后接回既有 `--replan-uat-failures` 路径
   - 必须复用或扩展现有 UAT orchestrator / verifier tests，而不是另起一套平行测试世界

5. **Gemini guardrail tests are mandatory**
   - 对 `gemini --list-sessions` 必须使用与真实当前 CLI 兼容的 mocked output
   - 必须验证错误 JSON 假设已被移除
   - 必须验证 session discovery failure 时进入 degraded / protected path

6. **Split flow sandbox tests are mandatory**
   - `resume --split` 必须验证：
     - authoritative active PR exists
     - current PR becomes superseded
     - existing planner slicing path is invoked
     - new slices enter queue
     - non-eligible states are rejected

7. **Prefer deterministic tests over live provider dependence**
   - 本次 quick-fix 以 deterministic local/sandbox tests 为主
   - live smoke 仅可作为 guardrail regressions 的补充，不是主质量门

### Quality Goal
本项目的质量目标不是“让 resume 在更多情况下看起来还能跑”，而是：
- 让 `resume` 基于 authoritative persisted recovery state 行为
- 让恢复路径从 heuristics guessing 迁移到 explicit contract
- 让 UAT recovery continuation、Gemini degraded behavior、split control 都依赖同一个恢复状态基础
- 让修复范围保持在 **resume-oriented bounded FSM contract**，而非扩张成全面 orchestrator 重构

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/agent_driver.py`
- `scripts/spawn_planner.py`（如 `--slice-failed-pr` / `--replan-uat-failures` / split 接线确有必要）
- `scripts/spawn_coder.py`（如 resume dispatcher 接线确有必要）
- `scripts/spawn_reviewer.py`（如 resume dispatcher 接线确有必要）
- `scripts/spawn_verifier.py`（如 verifier/UAT recovery state 接线确有必要）
- `scripts/config.py`（仅限 Gemini continuity guardrail 需要时）
- `scripts/structured_state_parser.py`（如需复用或扩展现有 PR 状态解析）
- 新增的小型恢复状态辅助模块（如 `resume_state.py` / `resume_dispatcher.py` / `resume_archive.py`）
- 与 resume / continuation / UAT recovery / orchestrator state 相关的测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft unified `ISSUE-1199`, `ISSUE-1209`, and `ISSUE-1210` under a single “Resume State Recovery and Control” quick-fix PRD.
- **Audit Rejection (v1.0)**: Auditor rejected the design because it attempted to recover by inferring state from scattered artifacts instead of defining one authoritative persisted recovery contract.
- **v2.0 Revision Rationale**: The architecture was tightened to require an explicit resume-oriented recovery state contract, explicit state-to-artifact mapping, deterministic state resolution rules, and bounded operator/engine guardrails built on top of that contract.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、状态枚举、文件名、配置键名等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**

### Exact State File Name
```text
resume_state.json
```

### Exact Transition Journal File Name
```text
resume_journal.jsonl
```

### Exact Persisted Recovery States
```text
PLANNER_ACTIVE
CODER_ACTIVE
REVIEWER_ACTIVE
MERGE_PENDING
VERIFIER_ACTIVE
UAT_RECOVERY_ACTIVE
COMPLETED_PASS
WITHDRAWN
BLOCKED
```

### Exact `resume_state.json` Required Keys
```json
{
  "schema_version": 1,
  "run_state": "PLANNER_ACTIVE|CODER_ACTIVE|REVIEWER_ACTIVE|MERGE_PENDING|VERIFIER_ACTIVE|UAT_RECOVERY_ACTIVE|COMPLETED_PASS|WITHDRAWN|BLOCKED",
  "mode": "mainline|uat_recovery|terminal",
  "current_pr_path": "string|null",
  "current_branch": "string|null",
  "baseline_commit": "string",
  "uat_report_path": "string|null",
  "recovery_attempt": "integer|null",
  "blocker_reason": "string|null",
  "last_transition_at": "ISO-8601 string"
}
```

### Exact Split-Eligible Persisted States
```text
CODER_ACTIVE
REVIEWER_ACTIVE
MERGE_PENDING
```

### Exact `--split` Argparse Help String
```text
Manual split of the current active PR during resume. Use this flag when the interrupted PR should not continue as-is and must be re-sliced into smaller follow-up PRs. Only valid when resume_state.json identifies a split-eligible active PR.
```
