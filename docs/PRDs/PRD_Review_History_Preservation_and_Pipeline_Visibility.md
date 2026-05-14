---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Review History Preservation and Pipeline Visibility

## 1. Context & Problem (业务背景与核心痛点)

当前 leio-sdlc 在两个相邻层面上存在可观测性与可追溯性缺口。

第一，Reviewer 的 canonical artifact `review_report.json` 会在同一个 SDLC run 内被后续 review 阶段覆盖。实际运行中，如果一个 PR 被 Reviewer 打回、继续修订，或者一个后续 PR 进入 review，新的 canonical report 会覆盖旧内容，导致 earlier review result 不再可恢复。这会直接削弱：
- 审计追踪能力；
- fatal / dead-end 复盘能力；
- manager handoff 的证据完整性；
- 对“是代码改好了才通过，还是后一个 Reviewer 结果覆盖了前一个 artifact”的判断能力。

第二，当前 pipeline 中若干“进入下一角色前就被打回”的流程路径对 channel 视角并不透明。用户可能看到 Coder 已经开始，但随后流程没有进入 Reviewer，或者 Reviewer 似乎没有得出正常结论，系统却已经开始重试/升级。外部观察者此时无法区分：
- 这是正常业务判定（如 Reviewer 明确 reject）；
- 还是流程本身故障（如 no output、invalid JSON、artifact missing、timeout）；
- 还是恢复性重入（如 Planner 对失败 PR 进行 split，或基于 UAT findings 自动重规划）。

这会造成两个问题：
1. manager / user 无法从 channel 视角理解系统当前为何回退、重试或重入；
2. 调试时容易把 transport/runtime/protocol failure 误判成普通业务回路。

本 PRD 需要同时解决这两个紧邻问题：
- 保留 review history，避免 canonical report 覆盖造成证据丢失；
- 提升 pipeline 在关键回退、故障、split/recovery 重入路径上的流程可见性。

## 2. Requirements & User Stories (需求定义)

### Scope Framing

#### Primary Objective
本 PRD 的主目标是：
1. 保留 append-only review history；
2. 让 reviewer 之前的 coder 回退原因，以及 reviewer 自身的协议/流程失败，对 channel 可见。

#### Secondary Objective
本 PRD 的次目标是：
1. 让 planner split re-entry 对 channel 可见；
2. 让 UAT-triggered recovery replanning 对 channel 可见；
3. 让 UAT recovery blocked / exhausted 与 verifier system error 的通知语义分离。

#### Scope Boundary
- 本 PRD 不是全 pipeline event taxonomy 重构。
- 本 PRD 不是新的持久化 recovery state model 设计。
- 本 PRD 只要求在现有 orchestrator 分支点补齐最关键的静默断点与 history preservation。

### Functional Requirements

#### R1. Preserve review history without changing the canonical contract
- 系统必须继续保留 `run_dir/review_report.json` 作为当前 canonical review artifact，避免本次 PRD 引发下游大范围契约重构。
- 每次 Orchestrator 成功读取并解析 canonical review report 后，必须额外复制一份不可覆盖的历史快照到 `run_dir/reviews/`。
- 历史文件命名必须至少包含：
  - PR 标识（来自当前 PR 文件 basename，不含扩展名）；
  - attempt 序号。
- 历史快照必须是 append-only；后续 review round 不得覆盖 earlier snapshot。

#### R1.1 Deterministic attempt rule
- `attempt` 必须定义为：*当前 PR 在当前 run 中第 N 次成功产出“可解析 canonical review report”并因此被归档成历史快照*。
- invalid JSON、missing artifact、`NOT_STARTED` placeholder、unknown assessment、non-zero exit、timeout 等失败 reviewer invocation，**不得**占用 snapshot attempt 序号。
- 因此，同一个 PR 的历史快照文件序号必须从 `1` 开始单调递增，且只对应“成功归档的 review snapshot”。

#### R2. Distinguish reviewer business rejection from reviewer pipeline failure
- Reviewer 正常产出合法 review JSON 且 verdict 表示需要修改时，仍应沿用既有 `review_rejected` 语义。
- 如果 Reviewer 本身发生协议/流程故障，则必须与 `review_rejected` 语义分离并发出独立通知。至少覆盖：
  - invalid JSON；
  - missing review artifact；
  - report remained `NOT_STARTED`；
  - unknown / unrecognized assessment；
  - reviewer exited non-zero 或同类异常执行失败。

#### R3. Expose coder pre-review fallback reasons to the channel
- 当 Coder 已结束但流程未进入 Reviewer，而是直接回到 yellow/red path 时，Orchestrator 必须向 channel 发送简短原因摘要。
- 本需求至少覆盖：
  - no effective output / null output；
  - unexpected dirty workspace / invalid workspace state；
  - coder exited non-zero；
  - coder timeout；
  - preflight failed（保留现有通知能力，不得退化）。

#### R4. Expose planner split / recovery re-entry to the channel
- 当系统对失败 PR 进行 split（包括 resume `--split` 和 State 5 失败后自动 split）时，Orchestrator 必须发出可见通知，说明：
  - 当前 PR 正在被 Planner 拆分；
  - 成功后原 PR 将被 superseded；
  - 若 split 成功，新的 smaller PRs 将继续进入执行队列。
- 当 split 失败（如未生成足够 slice、达到最大 slice depth、或 planner 执行失败）时，也必须发出明确通知或阻塞提示。

#### R5. Expose UAT-triggered recovery planning to the channel
- 当 UAT 产出 `NEEDS_FIX` 且存在 actionable findings，系统自动调用 Planner 基于 UAT findings 重规划时，Orchestrator 必须发出通知。
- 该通知应让外部明确知道：
  - 这不是普通新一轮初始规划；
  - 这是基于 UAT 发现项的 recovery replan。
- 当 UAT recovery 次数耗尽或进入人工阻塞状态时，通知语义不得与 verifier 系统错误混淆。

#### R6. Minimum required event/reason contract
本 PRD 不要求一次性重构所有 event taxonomy，但以下最小 event/reason contract 为必做范围。实现可以采用“细分 event type”或“generic event type + exact reason key”，但最终行为必须稳定覆盖以下语义：

- coder pre-review fallback:
  - `coder_no_output`
  - `coder_workspace_dirty`
  - `coder_failed`
  - `coder_timeout`
  - `preflight_failed`（existing behavior must remain valid）
- reviewer pipeline failure:
  - `reviewer_invalid_json`
  - `reviewer_no_output`
  - `reviewer_placeholder_stuck`
  - `reviewer_unknown_verdict`
  - `reviewer_failed`（generic fallback for non-subtyped reviewer execution failure）
- planner split visibility:
  - `planner_split_start`
  - `planner_split_complete`
  - `planner_split_failed`
- UAT recovery visibility:
  - `uat_recovery_plan_start`
  - `uat_blocked`
  - `uat_recovery_exhausted`
- existing business verdict semantics that must remain distinct:
  - `review_rejected`
  - `uat_complete`
  - `uat_error`（must remain reserved for verifier/runtime/protocol style system error, not generic blocked recovery）

### Non-Goals
- 不在本 PRD 中把 `review_report.json` 改造成新的唯一 source-of-truth 路径。
- 不在本 PRD 中引入 review history manifest / index 文件。
- 不在本 PRD 中重构完整 notification architecture。
- 不在本 PRD 中统一治理所有 runtime 角色的日志落盘协议。
- 不要求本次同时重构 Auditor、Slack transport 或 daemon/supervisor 架构。
- 不要求本次引入新的持久化 planner / UAT recovery 状态模型。

### User Stories
- 作为 manager，我希望在 channel 中看到“为什么流程没有进入 Reviewer 而是回退重试”，这样我不需要翻日志猜测系统在做什么。
- 作为 manager，我希望能区分“Reviewer 业务上 reject 了代码”和“Reviewer 自己跑坏了”，这样我能判断该看代码问题还是看 runtime/protocol 问题。
- 作为复盘者，我希望 earlier review report 在后续 review 之后仍可恢复，这样我能比较多轮评审差异并解释为什么流程演化成当前状态。
- 作为 manager，我希望在 split / UAT recovery replan 发生时收到通知，这样我知道原 PR 路径已经被 superseded 或 recovery logic 已经启动。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

本 PRD 明确采用“小步止血、保持兼容”的策略，而不是借机重构整个 artifact / notification 协议。

### Decision A — Keep canonical review_report.json, add append-only snapshots
- 继续保留 `run_dir/review_report.json` 作为 canonical latest review artifact。
- 不修改现有下游消费者对 canonical path 的依赖方式（如 Coder revision、merge path、现有 orchestrator flow）。
- 在 Orchestrator 成功解析 canonical review report 后，立即将其复制到：
  - `run_dir/reviews/<pr-id>.<attempt>.review.json`
- `pr-id` 应来自当前 PR 文件 basename 去扩展名，并做最小必要的文件名安全处理。
- `attempt` 必须遵循本 PRD 在 `R1.1 Deterministic attempt rule` 中定义的规则。

### Decision B — Notifications remain orchestrator-owned
- 本 PRD 不要求让 `spawn_reviewer.py`、`spawn_planner.py`、`spawn_verifier.py` 直接向 channel 写新增消息。
- 新增流程可见性通知应由 `orchestrator.py` 统一负责发出。
- 原因：
  - Orchestrator 最清楚当前是在 retry、resume、split、escalation 还是 blocked；
  - 便于把相同底层失败映射为一致的用户可见语义；
  - 可避免把 transport 逻辑继续扩散到各 role runtime 中。

### Decision C — Separate business verdicts from pipeline/runtime failures
系统必须在事件语义上明确区分三类情况：
1. 业务判定：例如 `review_rejected`、UAT `NEEDS_FIX`；
2. 流程/协议故障：例如 invalid JSON、missing artifact、timeout、non-zero exit；
3. 恢复性重入：例如 planner split、UAT recovery replan。

本次实现不要求引入复杂事件总线，但要求通知文案和 event type 能体现这三类区别，避免把所有失败都包装成“review 没过”或“UAT error”。

### Decision D — Scope the first implementation to high-value visibility points
本次实现优先覆盖这些高价值断点：
- coder 在 reviewer 前被打回的原因；
- reviewer 自身失败/协议故障；
- planner split re-entry；
- UAT recovery replan；
- review history preservation。

本次不要求一口气把所有内部状态机转移都做成 channel event feed。

### Decision E — Recovery visibility is notification-only in this slice
- 对 planner split 和 UAT recovery，本 PRD 只要求在现有 orchestrator 分支点发出 channel-visible summary notifications。
- 本 PRD 不要求引入新的 recovery persistence contract、额外状态机层、或新的 daemon/event-bus 机制。
- 若现有 resume_state / blocked path 已满足执行需要，本 PRD 的新增目标仅为“让外部看得见发生了什么”。

### Target Files / Modules
本 PRD 允许并预期修改以下模块（以实际最小必要修改为准）：
- `scripts/orchestrator.py`
- `scripts/spawn_reviewer.py`（仅在最小必要范围内配合 reviewer failure reason 暴露或测试契约时修改）
- `scripts/notification_formatter.py`
- `scripts/spawn_verifier.py`（仅在测试夹具或最小必要协议适配确有需要时允许修改）
- 相关 mocked / sandbox E2E tests

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Preserve review history across multiple review rounds for the same PR**
  - **Given** a single SDLC run where the same PR enters Reviewer more than once
  - **When** each successful Reviewer round produces a valid canonical `review_report.json` that can be parsed and archived
  - **Then** the run directory contains multiple distinct files under `run_dir/reviews/`
  - **And** each earlier review snapshot remains readable after later review rounds complete
  - **And** `run_dir/review_report.json` still exists as the latest canonical report

- **Scenario 2: Preserve review history across different PRs in the same run**
  - **Given** a single SDLC run processes PR A and later PR B
  - **When** both PRs successfully produce canonical review reports that are parsed and archived
  - **Then** `run_dir/reviews/` contains preserved snapshots for both PRs
  - **And** the later review for PR B does not overwrite PR A's historical review artifact

- **Scenario 3: Attempt numbering only advances for archived successful review snapshots**
  - **Given** a PR enters Reviewer multiple times in the same run
  - **And** one or more reviewer invocations fail with invalid JSON, missing artifact, `NOT_STARTED`, unknown assessment, timeout, or non-zero exit
  - **When** a later reviewer invocation finally produces a valid canonical review report that is archived
  - **Then** the archived snapshot uses the next sequential attempt number based only on prior archived successful snapshots
  - **And** failed reviewer invocations do not consume snapshot attempt numbers

- **Scenario 4: Notify when coder produced no effective output before review**
  - **Given** a PR enters Coder and the Coder round completes without effective code changes
  - **When** Orchestrator decides to retry before spawning Reviewer
  - **Then** the channel receives a concise notification explaining that the Coder produced no effective output
  - **And** the message is clearly framed as a retry-before-review event rather than a Reviewer rejection

- **Scenario 5: Notify when coder leaves unexpected workspace state before review**
  - **Given** a PR enters Coder and the resulting workspace state is not acceptable for advancing to Reviewer
  - **When** Orchestrator routes the flow back to retry or escalation before review
  - **Then** the channel receives a concise notification explaining that the Coder left an unexpected workspace state

- **Scenario 6: Notify when Reviewer fails to produce a valid review artifact**
  - **Given** a PR enters Reviewer
  - **When** Reviewer fails by producing invalid JSON, no artifact, a `NOT_STARTED` placeholder, or an unknown assessment
  - **Then** the channel receives a concise failure notification
  - **And** the notification is semantically distinct from a normal `review_rejected` business verdict

- **Scenario 7: Keep normal reviewer rejection semantics unchanged**
  - **Given** a PR enters Reviewer and Reviewer returns a valid review report whose assessment means the code needs changes
  - **When** Orchestrator processes that result
  - **Then** the channel still receives the existing rejection-style notification
  - **And** that notification is not mislabeled as a runtime or protocol failure

- **Scenario 8: Notify when Planner split starts and completes**
  - **Given** a failed PR is being re-entered through split recovery
  - **When** Orchestrator invokes Planner to split the PR into smaller slices
  - **Then** the channel receives a notification that split recovery has started
  - **And** if split succeeds, the channel receives a notification that the original PR has been superseded by newly generated slices

- **Scenario 9: Notify when Planner split fails**
  - **Given** a failed PR is routed into split recovery
  - **When** Planner fails to generate the required replacement slices or maximum split depth has been reached
  - **Then** the channel receives a failure or blocked notification explaining that split recovery did not succeed

- **Scenario 10: Notify when UAT triggers recovery replanning**
  - **Given** UAT returns `NEEDS_FIX` with actionable findings
  - **When** Orchestrator automatically invokes Planner to generate follow-up recovery PRs
  - **Then** the channel receives a notification stating that UAT-triggered recovery planning has started
  - **And** the notification makes clear that this is recovery replanning rather than initial PRD slicing

- **Scenario 11: Distinguish UAT recovery exhaustion/block from verifier system error**
  - **Given** UAT recovery cannot continue because retries are exhausted or the result requires human judgment rather than automatic replanning
  - **When** Orchestrator transitions the run into a blocked state
  - **Then** the channel notification does not mislabel that state as a verifier protocol/system error

- **Scenario 12: Preserve backward compatibility for existing canonical consumers and green path flow**
  - **Given** the pipeline follows a normal green path with valid reviewer output and successful merge/UAT progression
  - **When** the new history preservation and visibility enhancements are present
  - **Then** existing consumers can still rely on canonical `run_dir/review_report.json` without path migration
  - **And** the normal reviewer rejection path, merge path, and UAT PASS path continue to work without semantic regression

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
最大风险不是“消息没发漂亮”，而是：
- review history 仍然被覆盖，导致 acceptance 表面通过但审计证据依然丢失；
- notification 加了一些文案，但关键 yellow/red/recovery path 仍然静默；
- 新增 event 误把业务拒绝和 runtime failure 混淆，反而让 channel 语义更乱；
- 为了提升可见性而意外破坏 canonical consumer 或 green path。

### Verification Strategy
本需求应以 mocked / sandbox orchestration tests 为主，避免把验证依赖放在真实 LLM 随机性上。

必须重点验证：
1. *History preservation correctness*
   - 同一 PR 多轮 review；
   - 同一 run 多个 PR review；
   - earlier snapshot 不被 later report 覆盖；
   - attempt 仅对成功归档 snapshot 递增。
2. *Notification semantics correctness*
   - coder null output / dirty workspace / timeout / non-zero；
   - reviewer invalid JSON / missing artifact / placeholder stuck / unknown assessment；
   - planner split start / success / failure；
   - UAT recovery start / blocked / exhausted。
3. *Backward compatibility*
   - canonical `review_report.json` 仍可被现有流程消费；
   - 正常 reviewer rejection / normal merge / UAT pass 路径不得退化；
   - `uat_error` 不得被泛化滥用到非系统错误阻塞场景。

### Testing Levels
- 优先使用现有 mocked E2E orchestrator tests 扩展覆盖。
- 若已有 reviewer / orchestrator sandbox tests 可重用，应在同一风格下补充最小新增场景。
- 不要求本 PRD 为该需求新增 live LLM 测试作为门槛。

### Quality Goal
验收目标不是“实现了更多通知”，而是：
- manager 能从 channel 视角判断当前属于 reject、failure 还是 recovery；
- historical review evidence 在 run 内不再丢失；
- 正常 green path 不受影响；
- 新增 event/reason contract 不产生歧义或漂移。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/notification_formatter.py`
- `scripts/spawn_reviewer.py`（仅在最小必要范围内允许修改）
- `scripts/spawn_verifier.py`（仅在测试夹具或最小必要协议适配确有需要时允许修改）
- `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`
- 其他与本 PRD 直接相关的 mocked / sandbox orchestration tests（仅限最小必要范围）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft combining two tightly related fixes: preserve append-only review history while improving pipeline visibility for retry, failure, split, and UAT recovery paths.
- **v1.1 Revision Rationale**: Tightened scope boundaries, made attempt numbering deterministic, defined a minimum required event/reason contract, and explicitly preserved backward compatibility for canonical consumers.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Event / Reason Keys
```text
coder_no_output
coder_workspace_dirty
coder_failed
coder_timeout
preflight_failed
reviewer_invalid_json
reviewer_no_output
reviewer_placeholder_stuck
reviewer_unknown_verdict
reviewer_failed
planner_split_start
planner_split_complete
planner_split_failed
uat_recovery_plan_start
uat_blocked
uat_recovery_exhausted
review_rejected
uat_complete
uat_error
```

### Exact Review History Path Pattern
```text
run_dir/reviews/<pr-id>.<attempt>.review.json
```

### Exact Attempt Rule
```text
attempt increments only when a reviewer result is successfully parsed from canonical review_report.json and archived as a history snapshot; failed reviewer invocations do not consume attempt numbers.
```
