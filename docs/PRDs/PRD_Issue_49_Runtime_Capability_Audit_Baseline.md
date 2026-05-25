---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 49 Runtime Capability Audit Baseline

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 需要面对越来越多潜在的执行引擎与 CLI,但系统不可能也不应该无差别支持所有 CLI。当前真正缺少的不是“更多 CLI 接入代码”,而是一套统一、可复用、可审计的能力合同,用于判断一个候选 CLI 是否适合通过 ACP 支持 `leio-sdlc` 流程,以及这种支持应如何被表达、如何被后续 registry / routing / governance 消费。

Issue #50 已经通过 Gemini CLI 提供了第一份真实 ACP 验证样本,证明以下事情不是抽象猜想:
1. 一个 bounded ACP 验证流程可以产出结构化 verdict artifact,而不是只留下过程日志。
2. 负面结论(`blocked` / `partially_supported` / `not_suitable_at_this_stage`)可以是合法输出,不应被编码成默认测试失败。
3. `continuity_mode`、`handle_acquisition_strategy`、`resume_requires_same_runtime_state`、`fallback_policy`、`capability_surface` 等字段确实具有控制面决策价值。
4. 单引擎(当前为 Gemini CLI)的成功或失败结论必须保持 target-scoped,不得外推为对所有 CLI 的证明。

但当前 #50 的实现本质上仍更像“Gemini-first spike”,而不是正式的、schema-driven 的 CLI audit baseline。若不先把这一套 baseline 收敛成正式合同,后续 #63(Codex bounded audit)、#51(engine registry)、#52(runtime routing) 都会建立在不够稳定的语义与样本实现之上,继续漂移。

本 PRD 的目标不是接入新的 CLI,也不是推动多引擎生产集成,而是把现有 Gemini ACP spike 提炼成正式的 runtime capability audit baseline,使后续任意候选 CLI 都能被同一审计框架以有界、可比较、可决策的方式评估。

本 PRD 明确采用以下收紧原则:
- 在 ACP 模式下,session continuation support 只承认两类合同语义:
  1. **authoritative resume**: CLI / ACP lane 提供可用于受控 resume 的 authoritative session / continuation identifier。
  2. **unsupported**: 若不提供 authoritative identifier,则视为不支持 resumable ACP session。
- 不允许把 heuristic / inferred / locally guessed / prompt-illusion 式 continuation 计为 ACP resume support。
- 若某 CLI 的 ACP lane 无法提供 authoritative session id / continuation id,则该 CLI 在 ACP 合同层面不支持 resume session,即使其在对话体验上“看起来还能接着聊”。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 系统必须把现有 Gemini CLI ACP spike 提炼为正式的 **schema-driven CLI audit baseline**,而不是继续保持 Gemini-first one-off 验证脚手架形态。
2. 系统必须定义一个 machine-checkable 的 runtime capability audit schema,用于表达单个 target CLI 的结构化审计结论。
3. 该 schema 必须至少覆盖以下核心字段:
   - `target_cli`
   - `target_scope_note`
   - `validation_timestamp`
   - `connect_result`
   - `execute_turn_result`
   - `handle_capture_result`
   - `resume_once_result`
   - `failure_classification`
   - `continuity_mode`
   - `handle_acquisition_strategy`
   - `resume_requires_same_runtime_state`
   - `fallback_policy`
   - `capability_surface`
   - `final_verdict`
4. 系统必须把现有 Gemini reference path 的 verdict artifact 收敛为该 schema 的第一份 reference audit output。
5. 系统必须提供最小、可复用的 audit baseline code path,使后续其它 CLI(例如 Codex)可以在不重写第二套框架的前提下复用同一 bounded audit flow。
6. 系统必须明确规定 ACP continuation contract 只支持两种合同语义:
   - `authoritative_resume`
   - `unsupported`
7. 系统必须明确规定以下 resume 支持方式 **不属于** 合法 ACP continuation support:
   - heuristic discovery
   - inferred resume
   - local guess / local mapping guess
   - 仅凭 prompt/context illusion 的“续聊”
8. 系统必须把 authoritative handle acquisition contract 收紧为以下三类之一:
   - `protocol_native`
   - `explicit_returned_handle`
   - `unavailable`
9. 系统必须在无 authoritative handle 的情况下,将 resumable session 明确标记为 `unsupported`,而不得再把任何 mapped / inferred continuation 写入正式 verdict。
10. 系统必须把 target-scoped verdict 作为强制要求;任何结构化审计输出都必须明确指出结论只适用于当前 target CLI / path,不得默认泛化。
11. 系统必须允许 negative verdict 作为合法审计输出,包括但不限于:
   - `partially_supported`
   - `not_suitable_at_this_stage`
   - `blocked`
12. 系统必须保留足够薄的 baseline runner / probe / client 三层职责边界,以便后续 #63 在 baseline 之上新增第二目标 CLI 审计,而不被迫重写核心判分逻辑。
13. 系统必须把 Gemini 作为本 issue 的唯一 reference target,其作用是证明 baseline 可执行,而不是把 baseline 扩展成多 CLI registry / routing 系统。
14. 系统必须在仓库内提供最小 schema validation tests 与 reference sample artifacts,使 #49 具有可通过 SDLC 验收的可测试输出,而不只是纯文档。
15. 系统必须明确后续 #63(Codex audit)的默认规则: Codex audit 必须基于本 issue 产出的 baseline schema 与 baseline runner 执行,而不得自由定义第二套 contract。
16. 系统必须把 `target_scope_note` 视为正式 contract 的必填字段,并在代码侧 verdict authority 中与 schema 保持一致,而不得仅存在于 fixture/schema 侧。
17. 当前 baseline schema 在本 issue 内默认以 Gemini reference target 为唯一已验证 target;后续第二目标 CLI 的审计必须复用同一 schema 结构,但不得在本 issue 内提前把 schema 改造成面向多 target 的生产 registry。
18. `handle_acquisition_strategy` 的正式 verdict 值必须由 contract authority 显式映射为收紧后的 enum(`protocol_native` / `explicit_returned_handle` / `unavailable`),不得把模糊或混合语义直接暴露为最终 contract 值。
19. baseline schema 可以允许额外字段用于审计附加信息,但不得削弱或绕过必填 contract 字段与收紧后的枚举约束。
20. 若需要新增 reference sample artifact,应至少优先考虑新增一个 `unsupported-resume` sample,以显式固化“无 authoritative handle 即 unsupported”的合同语义。

### 2.2 Non-Functional Requirements
1. 本 issue 必须保持 scope 有界,不得演化为 multi-engine production integration。
2. 本 issue 必须是 **contract productization + baseline refactor** 问题,而不是 registry / routing / governance 功能问题。
3. 本 issue 必须与现有 direct CLI runtime path 并存,不得删除或隐式替换 legacy path。
4. 本 issue 必须优先复用 #50 已有实现成果,而不是推倒重写第二套 ACP 验证框架。
5. 本 issue 不得引入 broad plugin architecture、config-driven engine discovery、或大而全 runtime manager。
6. 本 issue 必须保持与既定 Python execution contract 一致,不得把环境准备、机器级安装、首次 auth 补齐等职责偷偷混入实现。
7. 本 issue 交付的 baseline 必须足够稳定,使后续 #63 能先判断“Codex 是否 fit 当前 baseline”,而不是默认允许 #63 边审计边随意改 contract。
8. 本 issue 必须明确区分:
   - “baseline schema 本身的正确性”
   - “单个 CLI 是否 fit baseline”
   - “是否需要后续 contract refinement”
9. 本 issue 必须让 #49 成为一个可以走 SDLC 的任务: 既有文档合同,也有代码、artifact 与测试产物。

### 2.3 User / Operator Stories
- 作为 `leio-sdlc` 的架构维护者,我希望把现有 Gemini ACP spike 收敛成正式的 CLI audit baseline,以便后续任何候选 CLI 都能按同一框架被判定是否值得支持。
- 作为后续 Codex 审计的执行者,我希望有一个稳定、可校验、不可随意漂移的 baseline schema 与 baseline runner,以便我能先判断 Codex 是否 fit,而不是自由发挥 contract。
- 作为后续 registry / routing 设计者,我希望 audit output 已经是结构化、target-scoped、可消费的,以便 #51 / #52 不需要再从一次性 spike 中猜 contract 语义。
- 作为对系统稳定性负责的 operator,我希望 ACP continuation contract 是保守且可审计的: 有 authoritative session id 才算 resumable support,否则就明确 unsupported,避免把不稳定的推论式续聊误当成可恢复 session。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 issue 采用“**schema-driven audit baseline refactor**”方案: 不是新增第二个目标 CLI,而是把 #50 已有的 Gemini ACP 验证实现提炼为正式的、可复用的 CLI audit baseline。

### 3.1 Baseline Productization Strategy
本 issue 不从零设计第二套合同系统,而是把现有 #50 的三层骨架收敛为正式 baseline:
- `scripts/acp_client.py`: thin ACP client boundary
- `scripts/acp_probe.py`: contract authority / verdict mapper
- `scripts/acp_smoke.py`: bounded audit runner (当前 reference target 为 Gemini)

核心重心切换如下:
- 现状: Gemini spike 是主,contract/schema 是其附属
- 目标: contract/schema-driven audit baseline 是主,Gemini 只是第一份 reference target

### 3.2 Contract Tightening for ACP Continuation
本 issue 明确收紧 ACP continuation contract:
1. authoritative session / continuation identifier 是 resume support 的唯一合法基础。
2. 只要缺少 authoritative identifier,则 resumable session 必须是 `unsupported`。
3. mapped / inferred / heuristic / prompt-illusion continuation 一律不得计为 ACP resume support。
4. `handle_acquisition_strategy` 仅允许:
   - `protocol_native`
   - `explicit_returned_handle`
   - `unavailable`
5. `continuity_mode` 在 ACP audit verdict 中仅允许:
   - `authoritative_resume`
   - `unsupported`
6. `resume_requires_same_runtime_state` 仍然保留,因为即便有 authoritative id,仍然可能存在是否依赖 same runtime state 的差异。

该收紧原则的意义在于:
- 防止把“看起来还能继续对话”误当成“可恢复 session”
- 防止后续 #51/#52 把不稳定 continuation 当成可路由能力
- 使 runtime contract 更保守、更稳定、更适合作为后续控制面输入

### 3.3 Schema-Driven Audit Baseline
本 issue 必须交付一个正式的 runtime capability audit schema。该 schema 至少需要满足:
- machine-checkable
- target-scoped
- 支持 positive / negative / blocked verdict
- 强制收紧 ACP continuation contract
- 支持 Gemini reference artifact 作为第一份 baseline evidence

实现策略如下:
1. 使用仓库内固定 schema 文件表达正式 audit contract。
2. 使用 reference sample artifact 表达 Gemini baseline result。
3. 使用最小 validation tests 校验 schema 与 sample 的一致性。
4. 用 `acp_probe.py` 作为 schema contract 的代码侧 authority,禁止继续让 Gemini-specific 弱语义漂移进正式 verdict。

### 3.4 Baseline Runner with Gemini as Reference Target
`acp_smoke.py` 需要从 Gemini-first smoke runner 提炼为 baseline audit runner,但当前仍只要求内建 Gemini reference target。目标不是支持第二个 CLI,而是让 runner 的职责从“Gemini 专属验证器”转向“单 target bounded audit runner”。

这意味着:
- 允许保留 Gemini-specific launch config 作为当前 reference target 常量
- 但 verdict 结构、artifact semantics、scope note、failure handling 必须体现 baseline contract
- 不要求本 issue 直接新增 Codex target
- 不允许在本 issue 中引入 registry / routing / plugin system

### 3.5 Files and Responsibilities
默认修改范围必须如下:
- `scripts/acp_client.py`
- `scripts/acp_probe.py`
- `scripts/acp_smoke.py`
- `tests/test_acp_client.py`
- `tests/test_acp_probe.py`
- `tests/test_acp_smoke.py`
- `tests/fixtures/acp_verdict_schema.json`
- `tests/fixtures/acp_verdict_gemini_sample.json`

可选新增文件(若需要,必须保持最小范围):
- `tests/fixtures/acp_verdict_blocked_sample.json`
- `tests/fixtures/acp_verdict_unsupported_resume_sample.json`

职责边界必须明确:
- `scripts/acp_client.py`: 仅负责 thin ACP interaction boundary,不得膨胀为多引擎 runtime manager
- `scripts/acp_probe.py`: 负责 #49 contract authority,即 observation → verdict 的唯一正式映射入口
- `scripts/acp_smoke.py`: 负责 bounded audit runner,当前 reference target 为 Gemini,同时负责产出 baseline reference artifact

### 3.6 Explicit Boundary Against Follow-up Issues
本 issue **不授权** 以下改动:
- 多 CLI config-driven engine registry (#51)
- `agent_driver` / orchestrator runtime routing 集成 (#52)
- corp/private CLI redaction/governance/hardening (#53)
- Codex target 实际接入与审计执行 (#63)
- broad plugin architecture / dynamic engine discovery

本 issue 只负责:
- baseline contract
- baseline schema
- Gemini reference baseline code path
- baseline tests / artifacts

### 3.7 Why This Design
该设计的核心取舍是:
- 让 #49 既不是纯文档,也不提前侵入 #63 / #51 / #52
- 把 #50 的实证结果收敛为正式 baseline,而不是让它停留在一次性 spike 状态
- 让 #63 能以“按 baseline 审 Codex”而不是“自由定义第二套合同”的方式推进
- 把 runtime contract 从“抽象讨论”变成“可执行、可测试、可被后续 issue 消费”的基线产物

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: #49 交付正式的 schema-driven audit baseline**
  - **Given** `leio-sdlc` 仓库中已经存在 #50 交付的 Gemini ACP spike 骨架
  - **When** 本 issue 完成
  - **Then** 仓库中必须存在正式的 runtime capability audit baseline,包括 schema、baseline code path、reference artifact 与最小 validation tests,而不是只留下文档说明

- **Scenario 2: ACP continuation contract 被收紧为 authoritative-or-unsupported**
  - **Given** 一个 ACP target CLI 被审计
  - **When** 系统尝试判断该 target 是否支持 resumable session
  - **Then** 只有存在 authoritative session / continuation identifier 时才可输出 `authoritative_resume`;若不存在 authoritative identifier,则 resumable session 必须输出 `unsupported`

- **Scenario 3: Heuristic / inferred continuation 不被计为正式支持**
  - **Given** 一个 CLI 在对话体验上“看起来还能继续”,但没有 authoritative session id / continuation id
  - **When** 系统产出正式 audit verdict
  - **Then** 该 CLI 不得被标记为支持 ACP resume session,且任何 heuristic / inferred / mapped continuation 都不得写入正式 support verdict

- **Scenario 4: Gemini reference artifact 成为 #49 baseline 的首个 reference audit output**
  - **Given** 当前 baseline reference target 为 Gemini CLI
  - **When** baseline runner 被执行或 reference sample 被验证
  - **Then** 必须能够得到一份符合 #49 schema 的 Gemini target-scoped audit artifact,作为 baseline 可执行性的参考证明

- **Scenario 5: Target scope 是强制要求**
  - **Given** 一个 runtime capability audit verdict
  - **When** verdict 被写出或校验
  - **Then** 它必须包含 target-scoped 信息,明确声明该结论只对当前 target CLI / path 成立,不得默认外推到其它 CLI

- **Scenario 6: Negative verdict 是合法输出**
  - **Given** 一个 CLI 在 handle、resume、prerequisite 或 capability 方面不满足 baseline contract
  - **When** 系统产出 audit verdict
  - **Then** 系统必须输出结构化的 `partially_supported`、`not_suitable_at_this_stage` 或 `blocked` 等合法结论,而不是仅以 traceback 或默认测试变红表达失败

- **Scenario 7: #49 不提前侵入 #63 / #51 / #52 的职责边界**
  - **Given** 本 issue 的目标是收敛 baseline contract
  - **When** Coder 完成本 issue 改动
  - **Then** 改动不得引入 Codex target 审计执行、engine registry、runtime routing、或 corp/private hardening 等后续 issue 负责的功能

- **Scenario 8: #63 必须能够把 #49 baseline 当作上游合同消费**
  - **Given** 后续会有第二个 CLI audit issue(#63)
  - **When** #49 完成
  - **Then** #49 产出的 schema-driven audit baseline 必须足以让 #63 默认按该 baseline 审计第二目标 CLI,而不是被迫自由定义第二套 contract

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
本 issue 的核心质量风险不是“代码跑不跑通”,而是:
1. 把 #50 的 Gemini-first spike 继续保留为样本实现,而没有真正收敛为正式 baseline。
2. 让不稳定的 heuristic / inferred continuation 混入正式 contract,从而污染后续 registry / routing 决策。
3. 让 #49 退化成纯文档,导致 #63 仍然需要自由发挥合同语义。
4. 让 #49 越界提前做掉 #63 / #51 / #52 的职责。

### 5.2 Test Strategy
本 issue 应采用“**schema + reference artifact + baseline tests**”三层验证策略。

#### A. Schema Validation Tests
必须至少验证:
- schema 必填字段齐全
- `continuity_mode` 值域被收紧
- `handle_acquisition_strategy` 值域被收紧
- `target_scope_note` 等 target-scoped 字段被强制要求
- `final_verdict` 允许 negative verdict
- schema 对 reference artifact 默认允许附加审计字段,但不会放松必填 contract 字段或收紧枚举的约束

#### B. Reference Artifact Validation
必须至少验证:
- Gemini reference sample artifact 能通过 schema
- blocked sample(如保留)能通过 schema
- unsupported-resume sample(如保留,建议新增)能通过 schema
- 无 authoritative handle 的 artifact 不会被误判为 resumable support

#### C. Baseline Code Tests
必须至少验证:
- authoritative handle → `authoritative_resume`
- unavailable / missing handle → `unsupported`
- heuristic / inferred / mapped continuation 不会进入正式 support verdict
- baseline runner 写出的 Gemini artifact 与 schema 一致
- `target_scope_note` 在代码侧正式进入 verdict contract,而不是只存在于 fixture/schema 中
- `handle_acquisition_strategy` 在代码侧被显式映射为收紧后的 enum,而不是保留模糊 mixed 值
- 默认测试不依赖新 target CLI、registry、routing 或真实第二引擎环境
- schema validation tests 可以使用最小 subset validator 或等价轻量校验方式,不强制新增重量级依赖,只要 contract 约束可重复校验即可

### 5.3 Quality Goal
该 issue 的质量目标是:
- 让 #49 成为真正可执行、可测试、可消费的 baseline issue
- 让 #63 有明确上游 contract 可依赖
- 让 #51 / #52 后续消费到的是保守、稳定、可审计的 runtime capability contract
- 让 ACP continuation contract 从“不稳定的推论语义”收敛为“authoritative-or-unsupported”的保守合同

## 6. Framework Modifications (框架防篡改声明)
本 PRD 授权修改以下文件类别:
- `scripts/acp_client.py`
- `scripts/acp_probe.py`
- `scripts/acp_smoke.py`
- `tests/test_acp_client.py`
- `tests/test_acp_probe.py`
- `tests/test_acp_smoke.py`
- `tests/fixtures/acp_verdict_schema.json`
- `tests/fixtures/acp_verdict_gemini_sample.json`
- 以及为 baseline schema validation 所必需的最小新增 fixture 文件(若需要)

本 PRD **不授权** 以下类别改动:
- `agent_driver` / orchestrator runtime routing 逻辑的大范围接入
- config-driven engine registry / engine discovery
- Codex target 的真实审计执行逻辑
- corp/private governance / redaction / hardening
- broad plugin system 或多引擎通用 runtime framework
- 删除或替换现有 legacy direct CLI path

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 #49 视为 runtime capability / continuity contract 的抽象设计问题,计划以文档和 schema 为主交付。
- **v1.1**: 基于 #50 已完成的 Gemini ACP spike,确认 #49 不能停留在纯文档层,必须把 #50 的现有实现收敛成 schema-driven CLI audit baseline,使 #49 具备可走 SDLC 的代码、artifact 与测试输出。
- **v1.2**: 收紧 ACP continuation contract: authoritative session id / continuation id 是 resumable support 的唯一合法基础; heuristic / inferred / mapped continuation 不得计为正式 ACP support。
- **v1.3**: 明确 #49 只负责 baseline contract / schema / Gemini reference baseline,不提前侵入 #63(Codex audit)、#51(registry)、#52(routing) 或 #53(governance) 的职责边界。
- **v1.4**: 吸收 coder-readiness 结果,补充 `target_scope_note` 必须进入代码侧正式 verdict contract,明确 `handle_acquisition_strategy` 需由 contract authority 显式映射为收紧后的 enum,澄清 baseline schema 当前以 Gemini 为唯一已验证 reference target,并允许 schema 保留附加审计字段而不放松核心 contract 约束。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`acp_continuation_contract_rule`**:
```text
For ACP-backed CLI audit, session continuation support is binary at the contract level: either the CLI exposes an authoritative resume identifier usable for controlled resume, or it does not support resumable sessions. Heuristic, inferred, mapped, or locally guessed continuation must not count as resumable ACP support.
```

- **`unsupported_resume_mode_value`**:
```text
unsupported
```

- **`authoritative_resume_mode_value`**:
```text
authoritative_resume
```

- **`allowed_handle_acquisition_strategy_values`**:
```text
protocol_native
explicit_returned_handle
unavailable
```

- **`required_reference_target_cli`**:
```text
Gemini CLI
```

- **`required_scope_note_rule`**:
```text
Every audit verdict must be target-scoped and must not be generalized from one CLI to another by default.
```

- **`forbidden_non_authoritative_continuation_support_terms`**:
```text
heuristic
inferred
mapped
local_guess
prompt_illusion
```
