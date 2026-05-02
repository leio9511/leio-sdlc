---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Control Plane Convergence Hardening

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 在处理高耦合控制面问题（resume / orchestration / recovery / split）时，当前存在两个上游收敛缺口，已经在近期真实执行中暴露：

1. **Retry / recovery 配置 overlay precedence 实现错误（ISSUE-1215）**
   - 预期语义应为：`default <- global <- local`。
   - 也就是：先使用默认值，再用全局配置覆盖，再仅在本地/项目配置存在时继续覆盖。
   - 当前实现的实际行为是：启动阶段读到一套配置，但进入 orchestrator 主循环后又重新写死默认值，并只在本地配置存在时覆盖；如果本地配置缺失，即使全局配置存在，也会错误回退到默认值。
   - 结果：全局配置被“本地缺失”错误抹掉，yellow / red / UAT recovery 相关节奏不可预测。

2. **Planner 对失败 PR 再切（`slice-failed-pr`）的输入上下文不足（ISSUE-1216 的可执行根因之一）**
   - 新版 planner playbook 已经增强了“收敛优先 / 最小完整切片 / mode-aware posture”的方法论。
   - 但在 `--slice-failed-pr` 模式下，planner 当前主要只拿到：
     - authoritative PRD
     - planner playbook
     - PR 模板
     - failed PR id / insert-after 约束
   - 它**没有被显式提供失败 PR contract 本身**作为 required reference。
   - 结果：planner 知道“要重切哪个编号”，但不知道“这个失败 PR 原本的边界和 contract 是什么”，只能依赖隐式推断，导致 re-slice 质量不稳定。

这两个问题表面上一个是 config bug，一个是 planner envelope 输入不足，但上层影响一致：

> **复杂 control-plane PR 的收敛节奏不稳定、行为不可预测、重切质量不足。**

本 PRD 的目标不是重写整个 orchestrator / planner 系统，而是做一个有边界的控制面收敛加固：
- 修正 retry / recovery 配置 overlay precedence，恢复可预测的策略执行；
- 补齐 `slice-failed-pr` 模式下 planner 的最小必要输入，让新版 playbook 真正有机会发挥作用。

本 PRD 统一处理：
- `ISSUE-1215`: SDLC orchestrator retry config precedence resets runtime settings inside main loop
- `ISSUE-1216`: Planner lacks fine-slice heuristics for control-plane PRs, causing oversized slices and poor reviewer-coder convergence

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. Orchestrator 必须对 retry / recovery 相关配置实现**单次解析、单次 overlay merge、全程复用**的语义。
2. Retry / recovery 配置的 precedence 必须严格为：
   - `default <- global <- local`
3. 如果 local/project config 缺失，系统必须保留已解析的 global 值，而不是错误回退到默认值。
4. Orchestrator 主循环不得再次通过硬编码默认值重置 `YELLOW_RETRY_LIMIT`、`RED_RETRY_LIMIT`、`max_uat_recovery_attempts`。
5. Planner 在 `--slice-failed-pr` 模式下，必须把**失败 PR contract 文件本身**作为 required reference 传给 planner。
6. Planner 在 `--slice-failed-pr` 模式下，必须仍然保留现有的 failed PR id / insert-after 约束，以保证新切片队列位置确定。
7. Planner 在 `--slice-failed-pr` 模式下，不得只依赖 PR 编号隐式猜测失败切片边界。
8. 新 envelope 输入必须与当前共享 planner playbook 兼容，不得为了 `slice-failed-pr` 引入第二份 planner playbook。
9. 本次不要求把 reviewer feedback 提供给 planner；planner 的最小必要输入是 failed PR contract，而不是 reviewer 的具体修正意见。

### Non-Functional Requirements
1. 本次修复必须保持为 **bounded hardening**，不得演变成全量 planner / orchestrator 架构重写。
2. 本次不引入新的 planner prompt protocol；应在现有 envelope 结构上做最小必要增强。
3. 本次不修改 coder / reviewer playbook，不调整 yellow/red 具体策略矩阵，只修正 1215 的配置读取错误与 1216 的 failed-PR re-slice 输入缺口。
4. 本次必须保留 planner playbook 的“项目无关性”：不能 hardcode `leio-sdlc` 文件名逻辑作为 planner 切分规则。
5. 所有变更必须有自动化测试覆盖，至少覆盖 config precedence 和 `slice-failed-pr` envelope required references。

### User Stories
- 作为 operator，我希望 retry / recovery 策略的运行节奏真正反映配置值，而不是被主循环中的默认值偷偷覆盖。
- 作为 operator，我希望当 local config 缺失时，global config 仍然生效。
- 作为 planner，我希望在 re-slice 失败 PR 时，能直接读到失败 PR contract 本身，而不是只靠 failed PR id 猜测上下文。
- 作为 manager，我希望 `slice-failed-pr` 的质量提升来自更完整的输入，而不是依赖模型“恰好足够聪明”。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Retry / Recovery Config Canonicalization
选择方案：**单次解析 + overlay merge + resolved config 全程复用**。

目标语义：
- 启动时构造一个 resolved config：
  - `defaults`
  - overlay `global config`
  - overlay `local/project config`（仅在存在时）
- orchestrator 主循环内只消费 resolved config 中的：
  - `YELLOW_RETRY_LIMIT`
  - `RED_RETRY_LIMIT`
  - `max_uat_recovery_attempts`
- 主循环中不再重新初始化这些值为字面默认值。

推荐改动边界：
- `scripts/orchestrator.py`
- 如有必要，可提取一个很小的 config overlay helper，但禁止借此扩张到全量 config 系统重构。

### 3.2 Planner `slice-failed-pr` Envelope Hardening
选择方案：**共享 playbook 不变 + 补 failed PR contract reference**。

目标语义：
- Planner 继续使用统一的 `planner_playbook.md`。
- `--slice-failed-pr` 模式下，envelope 除现有 authoritative PRD / playbook / template 外，额外增加：
  - `failed_pr_contract`
    - `kind: pr_contract`
    - `required: true`
    - `priority: 1`
    - `purpose: failed_slice_boundary_source`
- 现有 `failed_pr_id` / `--insert-after` 语义保留，用于队列位置锚定。
- Planner 仍然不读取 reviewer feedback，保持 planner/coder 输入职责边界清晰。

推荐改动边界：
- `scripts/spawn_planner.py`
- `scripts/planner_envelope.py`（如该适配层需要同步）
- `scripts/envelope_assembler.py`
- 对应 planner envelope / spawn tests

### 3.3 Explicit Out-of-Scope
本 PRD 明确不做：
- 不新增第二份 planner playbook
- 不把 reviewer feedback 传给 planner
- 不重设计 yellow/red policy
- 不修改 coder/reviewer prompt
- 不重构 full PRD standard mode / UAT mode envelope，除非测试需要极小兼容改动

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: global config remains effective when local config is absent**
  - **Given** runtime default values exist and global config sets non-default retry / recovery values
  - **And** local/project config is absent
  - **When** orchestrator starts and enters its main loop
  - **Then** it must continue using the global-config values
  - **And** it must not silently fall back to hardcoded defaults

- **Scenario 2: local config overrides global config only when present**
  - **Given** defaults exist, global config sets one value, and local/project config sets a different value
  - **When** orchestrator resolves retry / recovery settings
  - **Then** the final runtime values must reflect `default <- global <- local`

- **Scenario 3: slice-failed-pr passes failed PR contract as required planner input**
  - **Given** planner is invoked with `--slice-failed-pr <failed_pr_file>`
  - **When** the planner envelope is built
  - **Then** the failed PR contract file itself must appear in planner required references
  - **And** planner must still receive the failed PR ordering anchor / insert-after constraint

- **Scenario 4: planner re-slice no longer depends only on failed PR id**
  - **Given** a failed PR contract exists on disk
  - **When** planner is invoked in `slice-failed-pr` mode
  - **Then** the runtime input must explicitly identify the failed PR contract boundary as a required source
  - **And** the planner must not be forced to reconstruct that boundary solely from naming conventions

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险有两个：
1. **配置 overlay 语义修了表面，主循环仍在某处悄悄重置默认值**
2. **planner envelope 看起来加了字段，但 planner 实际 required references / rendered prompt 没体现出来**

测试策略：
- 以**单元/行为测试**为主，不需要跑整条 SDLC。
- 对 1215：
  - mock defaults/global/local 三层输入
  - 验证 resolved config 的 precedence 和 loop 使用值
- 对 1216 envelope：
  - 验证 `slice-failed-pr` 的 startup packet / rendered prompt / reference_index
  - 确认 failed PR contract file 被标成 required reference
- 如已有 planner spawn characterization tests，可补最小回归覆盖；无需在本 PRD 内引入真实 OpenClaw agent E2E 作为主验证手段。

质量目标：
- 运行时配置语义可解释、可预测
- `slice-failed-pr` 输入完整且职责边界清晰
- 不引入新的 prompt protocol 分裂

## 6. Framework Modifications (框架防篡改声明)
本 PRD 明确授权修改以下框架文件：
- `scripts/orchestrator.py`
- `scripts/spawn_planner.py`
- `scripts/planner_envelope.py`（如需）
- `scripts/envelope_assembler.py`
- 与 planner envelope / config precedence directly related 的测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 1215 与 1216 合并到同一控制面收敛加固 PRD。
- **v1.1**: 明确 1215 是 overlay precedence bug，不是泛化“配置重构”。
- **v1.2**: 明确 planner 不需要 reviewer feedback；`slice-failed-pr` 最小必要补丁是 failed PR contract required reference。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
