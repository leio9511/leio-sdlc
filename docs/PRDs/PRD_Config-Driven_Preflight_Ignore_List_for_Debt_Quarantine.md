---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Preflight Debt Quarantine via Config-Driven Ignore List

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前的 `preflight.sh` 被一批历史失败测试卡住，导致本地 SDLC 流程无法稳定推进。

我们已经做过一次本地临时验证，结果证明：只要把当前已知 failing files 临时隔离，`preflight.sh` 就可以恢复为 green。

这说明当前最缺的不是“再发明一个更复杂的 gate 变体”，而是一个更直接的、可测试的、可审计的**假绿机制**：

> 用一个外部配置文件承载当前已知被 quarantine 的测试文件，让 `preflight.sh` 在有 debt 的情况下仍然可以通过，但这个通过状态必须被明确地视为“debt quarantine green”，而不是“真实全绿”。

本 PRD 只做这一件事：

- 引入 `ignore_tests.json` 作为外部 ignore list；
- 让 `preflight.sh` 从该 JSON 读取当前被隔离的测试文件；
- 让 preflight 在 debt 存在时仍可通过；
- 让这个行为本身变成一个黑盒可测试的 contract。

本 PRD **不覆盖**：
- 后续逐批修复 quarantined 测试文件；
- 最终清零 ignore list；
- GitHub CI 接入；
- rescue mode；
- 其他 gate 设计。

**Boss Mandate / 特别授权背景**

Boss 明确允许在当前历史债务条件下，先引入一个外部配置驱动的 debt quarantine 机制，让 preflight 先恢复为“假绿”，从而解除 SDLC 被坏 gate 完全锁死的问题。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须引入外部 `ignore_tests.json` 作为唯一的临时 quarantine 数据面**
   - `preflight.sh` 不再硬编码一长串临时 skip/ignore 分支。
   - 临时隔离集合应从外部 JSON 读取。

2. **`ignore_tests.json` 必须 fail-closed**
   - 如果配置文件缺失、语法错误、格式错误、或包含未知结构，preflight 必须失败，而不是静默忽略。
   - 这是一个 gate 配置，不允许模糊行为。

3. **`ignore_tests.json` 必须支持按测试类型分组**
   - 至少支持：
     - `bash`
     - `pytest`
   - 每个分组都是一个文件路径列表。

4. **`preflight.sh` 必须根据 ignore list 产生一个可通过的“debt quarantine green”**
   - 当 ignore list 非空时，preflight 允许跳过其中列出的文件。
   - 这个通过状态是有 debt 语义的，不得被误判为真实全绿。

5. **必须有一个清晰的 black-box contract 来验证 ignore 行为**
   - 可观察地验证：
     - 给定一份 ignore list，预期被列出的测试不会执行；
     - 给定空 ignore list，预期恢复完整测试执行。

6. **必须给出当前已知 failing files 的精确 seed manifest**
   - 本 PRD 要把当前已知要 quarantine 的文件写死到初始 `ignore_tests.json` 中。
   - 不允许用“minimal example”代替当前真实 seed。

7. **ignore list 是临时 debt quarantine，不是永久白名单**
   - 它存在的目的是恢复 preflight 的可用性。
   - 最终目标仍然是把它清零，但这不属于本 PRD 的范围。

### User Stories

- **As an SDLC operator**, when preflight is blocked by known historical failures, I want a configuration-driven quarantine list so the gate can return to a controlled green state.
- **As a maintainer**, I want the quarantine list to live in data, not code, so it is auditable and reusable.
- **As an architect**, I want the gate to fail closed when the configuration is malformed, so the quarantine mechanism itself does not become a hidden footgun.
- **As a reviewer**, I want the quarantine green to be explicitly distinguishable from a true green so the gate semantics remain honest.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用**配置驱动的 debt quarantine**。

### 3.1 设计原则

1. **把 bypass 从代码逻辑里拿出来，放进数据面**
   - `preflight.sh` 读取 `ignore_tests.json`。
   - 不再把当前临时 bypass 硬编码进主逻辑分支。

2. **把“假绿”变成显式、可测试的 contract**
   - preflight 仍然可以通过，但它的通过是带 debt 语义的。
   - 这个行为必须可观察、可验证、可审计。

3. **fail-closed**
   - ignore 配置坏了，gate 必须失败。
   - 不允许因为配置异常而默默进入“看起来绿”的错误状态。

### 3.2 `ignore_tests.json` 结构

建议采用如下结构：

```json
{
  "bash": [
    "scripts/test_planner_slice_failed_pr.sh"
  ],
  "pytest": [
    "tests/test_orchestrator_session_strategy.py",
    "tests/test_079_agent_driver_openclaw_lazy_create.py",
    "tests/test_083_openclaw_model_aware_routing.py",
    "tests/test_handoff_integration.py",
    "tests/test_orchestrator_handoff.py",
    "tests/test_planner_envelope_forward_compatibility.py",
    "tests/test_spawn_auditor.py"
  ]
}
```

### 3.3 `preflight.sh` 行为

- Bash 测试：跳过 JSON 中列出的脚本文件；
- Pytest 测试：通过 `--ignore=<file>` 忽略 JSON 中列出的测试文件；
- ignore list 为空时，恢复正常完整测试执行；
- 配置文件缺失或格式错误时，preflight 必须 fail-closed。

### 3.4 目标修改点

本 PRD 允许修改：
- `leio-sdlc/preflight.sh`
- `leio-sdlc/ignore_tests.json`（新增）
- 与 ignore 行为直接相关的最小验证测试文件（新增）

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Non-empty ignore list produces debt-quarantine green**
  - **Given** a valid non-empty `ignore_tests.json`
  - **When** `preflight.sh` is executed
  - **Then** the tests listed in the JSON are skipped/ignored
  - **And** preflight completes successfully

- **Scenario 2: Empty ignore list restores full preflight**
  - **Given** an empty `ignore_tests.json`
  - **When** `preflight.sh` is executed
  - **Then** it runs the full normal test surface
  - **And** it behaves like a standard preflight gate

- **Scenario 3: Malformed ignore configuration fails closed**
  - **Given** `ignore_tests.json` is missing or malformed
  - **When** `preflight.sh` is executed
  - **Then** preflight fails instead of silently bypassing the configuration problem

- **Scenario 4: Quarantine green is distinguishable from true green**
  - **Given** the ignore list is non-empty
  - **When** `preflight.sh` succeeds
  - **Then** the result is treated as debt-quarantine green, not true full green

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是某个测试被隔离，而是 quarantine 机制本身变成一个不受控的长期白名单，从而让 preflight “看起来绿”但实际上隐藏债务。

### Verification Strategy

1. **Config-driven behavior tests**
   - 验证非空 ignore list 能产生 debt-quarantine green。
   - 验证空 ignore list 能恢复完整 preflight。

2. **Fail-closed tests**
   - 验证缺失 / malformed JSON 会导致 preflight 失败。

3. **Seed manifest verification**
   - 验证当前已知 failing files 的 seed manifest 被精确加载并产生预期 quarantine 效果。

### Quality Goal
本 PRD 的目标是把现有 hack 变成一个**可测试、可审计、fail-closed 的 debt quarantine 机制**。它不是最终真绿，但它让当前 preflight 可以在债务存在时恢复为一个明确的、可解释的 green 状态。

## 6. Framework Modifications (框架防篡改声明)
- `leio-sdlc/preflight.sh`
- `leio-sdlc/ignore_tests.json`（新增）
- `leio-sdlc/tests/` 下与 ignore 行为相关的最小验证测试（新增）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0-v8.0**: 尝试 temporary-green / rescue mode / branch-local self-repair 等方案，但都在主 gate 语义上过重，且难以形成可测试 contract。
- **v9.0**: 实证确认当前已知 failing-file 集合足以恢复 preflight 通过。
- **v10.0 Revision Rationale**: 收缩为配置驱动的 debt quarantine：把临时 bypass 从硬编码脚本逻辑中拿出来，改成一个 fail-closed 的外部 ignore list，使 preflight 在 debt 存在时仍能恢复为明确的 quarantine green。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`ignore_json_filename`**:
```text
ignore_tests.json
```

- **`ignore_json_seed`**:
```json
{
  "bash": [
    "scripts/test_planner_slice_failed_pr.sh"
  ],
  "pytest": [
    "tests/test_orchestrator_session_strategy.py",
    "tests/test_079_agent_driver_openclaw_lazy_create.py",
    "tests/test_083_openclaw_model_aware_routing.py",
    "tests/test_handoff_integration.py",
    "tests/test_orchestrator_handoff.py",
    "tests/test_planner_envelope_forward_compatibility.py",
    "tests/test_spawn_auditor.py"
  ]
}
```

- **`fail_closed_statement`**:
```text
If ignore_tests.json is missing or malformed, preflight must fail closed.
```

- **`quarantine_green_statement`**:
```text
A non-empty ignore list may produce debt-quarantine green, which is distinct from true full green.
```
