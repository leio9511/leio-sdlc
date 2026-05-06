---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Coder Null-Output Recovery via Existing Yellow and Red Paths

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前已经暴露出一种高风险但隐蔽的 SDLC 控制面缺陷：**coder 回合可以在没有真实实现产物、没有显式失败 handoff 的情况下结束，而 orchestrator 仍然把这一轮当成有效完成并继续推进到 reviewer。**

在真实 run 中，这个缺陷至少表现为两种相关失败模式：

1. **acknowledgment-only completion**
   - coder 读取 prompt / PR contract / PRD / playbook 后，只回复类似：
     - “I have read the instructions”
     - “I’m ready for the next step”
   - 但不写代码、不跑测试、不提交 commit、也不显式失败。

2. **active work without progress**
   - coder 开始尝试真正的文件 / 工具操作，甚至进入 stalled 状态；
   - 但最终没有可审查 artifact、没有 commit、没有 failure handoff；
   - reviewer 只能看到 empty diff 并基于“未实现” reject。

当前 orchestrator 对 coder round 的完成判定过于宽松。现有检查大致集中在：

- coder 子进程 return code
- 工作区是否 dirty
- `preflight.sh` 是否失败

但缺少一个关键事实检查：

> **本轮 coder 是否真的产出了实现进展，或至少产出了显式失败。**

在当前 preflight debt / temporary green / soft-gate 环境下，这个缺陷会显著放大 SDLC 大规模改动的不可信性。因为即使 preflight 没炸、工作区也干净，也不代表 coder 真的完成了本轮实现。

本 PRD 的目标不是重写整个 orchestrator 状态机，也不是发明一条全新恢复流程，而是：

> **把 coder null-output 检测接入现有 yellow / system_alert → red path 机制，使其成为一种可自动恢复、有限重试、最终沿既有 red path 升级的框架级故障。**

也就是说：

- 第一次 / 第二次 null-output 不应直接 handoff 给 manager；
- 应先通过现有 system_alert / yellow path 自动打回 coder；
- 若重试耗尽，则沿现有 red path 升级，而不是另造新流程。

本 PRD 不覆盖：

- reviewer / verifier 的类似 null-output 问题
- true-green preflight debt 修复
- 全新的失败状态机分支或新的 manager handoff protocol
- prompt-only 解决方案（prompt 强化可作为辅助，但不是主修复）

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须新增 coder null-output 检测**
   - 在 coder round 完成后、reviewer 启动前，orchestrator 必须检测本轮是否存在真实实现进展。

2. **必须复用现有 yellow / system_alert 恢复机制**
   - 当检测到 null-output 时，不得直接进入 reviewer；
   - 不得直接 handoff 给 manager；
   - 必须通过现有 `system_alert_text` / yellow path 机制将该轮打回 coder。

3. **必须复用现有 red path 升级机制**
   - 当 null-output 恢复重试耗尽后，不得发明新的升级流程；
   - 必须沿现有 red path / state-5 escalation 路径处理。

4. **必须定义 null-output 的最小判定 contract**
   - 第一版至少基于以下事实进行判定：
     - coder return code 为 0
     - 无工作区文件 delta
     - 无 commit delta
   - 满足上述条件时，视为 invalid coder completion。

5. **必须禁止 acknowledgment-only completion 被视为成功**
   - 诸如：
     - “I’m ready for the next step”
     - “I understand the task”
     - “I have read the instructions”
   - 这类仅确认/准备状态，如果没有实现产物或显式失败，不得被视为完成。

6. **必须提供专用 JIT corrective prompt**
   - 该 prompt 必须明确指出上一轮无效；
   - 必须要求 coder 在当前分支状态上继续自主执行并产出真实实现产物；
   - 不得把“自由文本式显式失败”作为 v1 的正式完成语义引入控制面。

7. **必须让主验证测试在当前 preflight 基线上真实执行**
   - null-output recovery 的核心 pytest 测试必须放在当前未被 `ignore_tests.json` quarantine 的测试文件中；
   - 不得把本 PR 的关键验证逻辑写入任何当前已被 ignore 的测试文件。

### Non-Functional Requirements

1. **不得新增平行恢复流程**
   - 本修复应尽可能接入现有 yellow / red path，而不是发明新的状态机分叉。

2. **主修复必须在控制面**
   - prompt 强化可以做，但不能替代控制面事实检查。

3. **恢复逻辑必须有限次**
   - null-output 重试不得无限循环。
   - 应复用现有 retry counter / escalation 机制。

4. **不得把无产物 round 推进到 reviewer**
   - reviewer 不应继续为空 diff 做“正常评审”。

### User Stories

- **As an orchestrator maintainer**, I want coder null-output rounds to be detected before reviewer starts so empty-diff reviews stop masquerading as normal SDLC progress.
- **As a manager**, I want the framework to auto-recover coder no-op rounds using the existing retry machinery instead of escalating immediately to me.
- **As a reviewer**, I want to review actual implementation artifacts, not act as the first detector of a zero-output coder turn.
- **As an architect**, I want this fix to strengthen the control plane without inventing a parallel failure-recovery model.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用**control-plane artifact checkpoint + existing yellow/system_alert reuse + existing red-path escalation** 的策略。

### 3.1 核心设计原则

1. **主修复在控制面，不在 prompt 层**
   - prompt 可以降低模型进入 acknowledgment-only posture 的概率；
   - 但真正的 correctness 必须由控制面对“是否有产物 / 是否有失败”做事实裁决。

2. **null-output 是现有恢复体系中的一种 recoverable coder failure**
   - 它不是正常 review finding；
   - 也不是一条全新流程；
   - 它应作为现有 yellow/system_alert retry 能处理的故障接入。

3. **红路径不是 manager 直升机，而是既有恢复上限后的升级**
   - 只有自动纠偏耗尽，才应进入现有 red path；
   - 不应在第一次 null-output 时就 manager handoff。

### 3.2 目标修改范围

本 PRD 允许修改：

- `leio-sdlc/scripts/orchestrator.py`
- 如确有必要，与 coder continuation / system-alert 注入直接相关的最小 supporting 脚本
- 与 null-output 检测和恢复语义直接相关的最小测试文件

测试文件约束：

- 本 PRD 的主验证测试必须新增在**当前未被 `ignore_tests.json` quarantine 的 pytest 文件**中；
- 不得把核心 null-output recovery 测试写入任何当前已被 ignore 的测试文件；
- 推荐新增专用测试文件，例如：`tests/test_orchestrator_coder_null_output_recovery.py`；
- 其目的就是确保在当前 temporary-green / quarantine 基线下，这些测试仍然会被真实 preflight 执行。

本 PRD 不授权：

- 重写整个 orchestrator 状态机
- 新建完全独立的 failure pipeline
- 大规模修改 coder/reviewer/verifier 提示体系
- 借机处理无关 preflight/CI 历史债务

### 3.3 Null-output 判定合同

第一版 null-output 检测至少基于以下事实：

1. coder 子进程 return code 为 0；
2. 当前工作区无 file delta（`git status --porcelain` 为空）；
3. 当前 HEAD 相比本轮 coder 启动前无 commit delta。

当且仅当以上条件同时成立时：

> **本轮 coder 回合被判定为 null-output / invalid coder completion。**

其语义是：

- 不是成功完成；
- 不是可进入 reviewer 的正常完成；
- 也不是立即 manager handoff；
- 而是一个应进入现有 yellow/system_alert 恢复路径的可恢复失败。

说明：

- 第一版不把自由文本式“blocker 说明”或“failure handoff”纳入控制面判定合同；
- 这一版只允许 orchestrator 基于自己已经拥有的确定事实（return code、git state、commit state）做机器判定；
- 如未来要支持显式 blocker 语义，必须另行定义固定 artifact 路径、schema、producer 与 parser，而不能依赖自由文本推断。

### 3.4 恢复策略（接入现有 yellow / system_alert）

当检测到 null-output 时，orchestrator 必须：

1. 不启动 reviewer；
2. 递增现有 yellow/retry counter；
3. 通过 `system_alert_text` 向 coder 注入 corrective JIT prompt；
4. 重新进入现有 coder 重试路径；
5. 若达到现有 yellow/retry 上限，则进入现有 red path / state-5 escalation。

不得：

- 为 null-output 新发明独立的状态机主分支；
- 在第一次或第二次 null-output 时直接 handoff manager；
- 把 null-output 伪装成 reviewer rejection。

### 3.5 JIT corrective prompt 语义要求

该 prompt 必须明确表达：

- 上一轮 coder 回合无效；
- 无文件 delta、无 commit delta；
- acknowledgment-only completion 不被接受；
- coder 必须继续自主执行并产出真实实现产物；
- 若继续 silent non-progress，将沿现有恢复/升级路径处理。

该 prompt 不得：

- 把自由文本式“显式失败”引入为 v1 的正式完成语义；
- 暗示 coder 只要给出 narrative blocker explanation 就算完成；
- 创造一个 orchestrator 当前并未正式支持的新 failure protocol。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Null-output coder round does not advance to reviewer**
  - **Given** a coder round that exits 0 but leaves no file delta, no commit delta, and no explicit failure handoff
  - **When** orchestrator evaluates coder completion
  - **Then** reviewer is not spawned
  - **And** the round is treated as invalid coder completion rather than normal success

- **Scenario 2: Null-output coder round is retried through existing system-alert path**
  - **Given** a coder round classified as null-output
  - **When** orchestrator prepares recovery
  - **Then** it reuses the existing `system_alert_text` / yellow-path mechanism to send a corrective retry to coder
  - **And** it does not invent a separate recovery pipeline

- **Scenario 3: Corrective retry forbids acknowledgment-only completion and demands artifact progress**
  - **Given** a corrective retry triggered by null-output detection
  - **When** coder receives the JIT system alert
  - **Then** the prompt requires continued autonomous execution toward real implementation artifacts
  - **And** acknowledgment-only completion is stated to be invalid
  - **And** the prompt does not invent a new free-form failure protocol unsupported by the current orchestrator

- **Scenario 4: Repeated null-output escalates through the existing red path**
  - **Given** repeated null-output coder rounds that exhaust the existing retry budget
  - **When** orchestrator can no longer auto-recover
  - **Then** it enters the existing red-path escalation machinery
  - **And** it does not jump directly to a manager handoff on the first null-output round

- **Scenario 5: Real coder success still follows the normal path**
  - **Given** a coder round that produces real implementation artifacts or a new commit
  - **When** orchestrator evaluates coder completion
  - **Then** the normal preflight/reviewer path continues unchanged

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是“多重试一次 coder”，而是：

1. 让无产物 coder round 继续流入 reviewer；
2. 用 prompt 祈祷替代控制面事实检查；
3. 为 null-output 新发明一条与现有 yellow/red path 平行的恢复系统；
4. 在没有 manager 恢复动作的情况下过早把框架级失败升级给 manager。

### Verification Strategy

#### A. Control-plane unit / integration verification
验证 orchestrator 在 coder→reviewer 之间的判定逻辑：

- 零 file delta + 零 commit delta（在 coder return code 为 0 的前提下）→ 识别为 null-output；
- null-output 不进入 reviewer；
- null-output 进入现有 system_alert / yellow retry；
- 重试耗尽进入现有 red path。

落地约束：

- 这一层的核心 pytest 测试必须放在当前未被 `ignore_tests.json` quarantine 的测试文件中；
- 推荐新增专用文件：`tests/test_orchestrator_coder_null_output_recovery.py`；
- 不得把本 PRD 的主验证逻辑藏入当前已被 ignore 的测试文件，否则在现有 temporary-green 基线下将无法形成真实 gate。

#### B. Prompt / alert contract verification
验证注入给 coder 的 JIT corrective prompt：

- 明确指出上一轮无效；
- 明确要求继续自主执行并产出实现产物；
- 明确禁止 readiness/acknowledgment-only completion；
- 不引入 orchestrator 当前未正式支持的自由文本 failure protocol。

#### C. Regression protection
必须确保：

- 正常有产物的 coder round 不受影响；
- preflight failed / dirty workspace 等现有 yellow path 行为不被破坏；
- reviewer action-required 路径不被混淆成 null-output 路径。

### Mocking / Sandbox Guidance
- 推荐使用最小 sandbox / mocked orchestrator flow 来构造：
  - coder exit 0 but no delta
  - coder exit 0 with delta
  - coder exit non-zero
- 不需要 live LLM 作为主验证手段；
- 主体 correctness 必须来自控制面可重复测试。

### Quality Goal
本 PRD 的质量目标是：

> **确保 leio-sdlc 不再把“无文件改动、无 commit、无显式失败”的 coder 回合当成正常完成，而是通过现有 yellow/system_alert→red path 机制进行自动纠偏与升级。**

## 6. Framework Modifications (框架防篡改声明)
- `leio-sdlc/scripts/orchestrator.py`
- 如确有必要，与 coder continuation / system-alert 注入直接相关的最小 supporting 脚本
- 与 null-output 检测和恢复语义直接相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 把 null-output 视为应立即 fail fast 给 manager 的错误。
- **Critique**: manager 没有有效恢复动作，过早 handoff 只会把控制面故障外包给 manager。
- **v2.0 Revision Rationale**: 改为接入现有 yellow/system_alert→red path；null-output 先自动纠偏，重试耗尽后再沿既有 red path 升级。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`recommended_primary_test_file`**:
```text
tests/test_orchestrator_coder_null_output_recovery.py
```

- **`non_ignored_test_rule`**:
```text
The primary null-output recovery tests must be added in a pytest file that is not currently listed under ignore_tests.json quarantine.
```

- **`null_output_system_alert`**:
```text
SYSTEM ALERT: Your previous coder round produced no implementation artifacts.

Detected state:
- no file delta
- no commit delta

This means your previous round is INVALID for SDLC automation.
Acknowledgment-only completion (for example “I’ve read the task”, “I’m ready”, or similar readiness/status-only replies) does NOT count as progress.

You must continue autonomously from the current branch state and produce real implementation artifacts that satisfy the PR contract:
- create/modify the required files
- run the relevant tests and ./preflight.sh if required
- commit the changed files
- leave git status clean
- report the new HEAD commit hash

Forbidden outcomes:
- “I’m ready for the next step”
- “I understand the task”
- any status-only or acknowledgment-only response without implementation artifacts

A narrative explanation without code, tests, and commit does not count as successful completion.
If you again produce no implementation artifacts, the orchestrator will escalate through the existing recovery path.
```

- **`null_output_detection_contract`**:
```text
coder return code = 0
AND git status --porcelain is empty
AND HEAD commit hash is unchanged for the coder round
=> classify as null-output / invalid coder completion
```

- **`null_output_recovery_policy`**:
```text
Do not spawn reviewer.
Route the round back through the existing system_alert / yellow-path retry mechanism.
If retry budget is exhausted, escalate through the existing red path.
```
