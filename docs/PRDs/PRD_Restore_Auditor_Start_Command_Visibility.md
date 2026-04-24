---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Restore Auditor Start Command Visibility

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` currently emits an `auditor_start` notification when `spawn_auditor.py` launches a PRD audit. The launch context already includes both `prd_file` and the fully rendered `command` string.

However, the current notification rendering path regressed in observability:
- `spawn_auditor.py` still passes `command` into the notification layer,
- but `notification_formatter.py` only renders `prd_file` for `auditor_start`,
- so the channel no longer shows the explicit startup command.

This is not an Auditor execution failure. The Auditor still starts normally. The defect is that the startup command is invisible in the channel, which weakens remote observability and makes first-line debugging slower.

The concrete operational damage is:
1. humans cannot immediately verify the exact Auditor invocation from the channel,
2. parameter/path mistakes become harder to diagnose without opening logs,
3. a previously visible command trace disappeared, creating confusion about whether the startup flow changed.

This PRD is therefore a narrow observability-regression hotfix. It must restore explicit command visibility for `auditor_start` without broad notification-system refactoring.

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. When `event_type = auditor_start` and the notification context includes `command`, the rendered message must explicitly include the command line.
2. The rendered message must continue to include the target `prd_file`.
3. When `command` is absent or empty, the formatter must degrade safely and still render a valid Auditor start message.
4. The fix must preserve the existing event contract that `spawn_auditor.py` passes structured context into the formatter.
5. The solution must not require changes to channel routing, Slack delivery plumbing, or the Auditor launch sequence itself unless strictly necessary.

### Non-Functional Requirements
1. This must remain a low-blast-radius fix.
2. The implementation must be backward compatible with existing `auditor_start` callers.
3. The change must improve operator observability without expanding into a larger notification redesign.
4. The regression must be locked by tests so future template refactors cannot silently remove the command line again.

### Explicit Boundaries
- **In Scope**:
  - `auditor_start` notification rendering
  - regression tests for formatter behavior
  - minimal supporting test updates if current expected strings encode the regression
- **Out of Scope**:
  - refactoring the whole notification formatter
  - redesigning all start-event messages
  - changing `spawn_auditor.py` launch semantics
  - changing Auditor approval/rejection logic
  - Slack-specific formatting redesign beyond restoring the lost command visibility

## 3. Architecture & Technical Strategy (架构设计与技术路线)
This issue is a classic presentation-layer regression, not a control-plane failure.

### 3.1 Root Cause
The upstream producer is already correct:
- `spawn_auditor.py` emits `auditor_start`
- context already contains `command`

The regression exists in the rendering layer:
- `scripts/notification_formatter.py`
- branch: `event_type == "auditor_start"`
- current behavior: renders only `prd_file`
- missing behavior: does not render `command`

### 3.2 Correct Fix Strategy
The correct fix is to repair the `auditor_start` formatter template directly.

Why this is the right layer:
1. the data is already available,
2. the formatter owns presentation responsibility,
3. changing callers would duplicate presentation logic and violate separation of concerns.

### 3.3 Implementation Direction
The `auditor_start` branch in `notification_formatter.py` must:
1. read `prd_file` from context as it does today,
2. read `command` from context,
3. if `command` is present and non-empty, render a two-line message,
4. otherwise fall back to the existing one-line message.

This preserves backward compatibility while restoring observability.

### 3.4 Test Strategy at the Code Level
Existing formatter tests currently encode the regressed output string. Those tests must be updated so they assert the intended restored behavior instead of preserving the bug.

At minimum the test suite must cover:
1. `auditor_start` with `prd_file` + `command`
2. `auditor_start` with `prd_file` only
3. unchanged rendering for unrelated event types

### 3.5 Authorized File Targets
The intended file targets are narrowly limited to:
- `scripts/notification_formatter.py`
- `tests/test_notification_formatter.py`

No other framework file should be modified unless a downstream test reveals a directly dependent expectation that must be updated to reflect the restored contract.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Auditor start message restores command visibility**
  - **Given** `spawn_auditor.py` emits an `auditor_start` event with both `prd_file` and `command`
  - **When** the notification is formatted for channel delivery
  - **Then** the final rendered message includes the Auditor start line and a second line showing the command

- **Scenario 2: Missing command degrades safely**
  - **Given** an `auditor_start` event contains `prd_file` but no `command`
  - **When** the notification is formatted
  - **Then** the formatter returns a valid one-line Auditor start message without crashing and without rendering `None`

- **Scenario 3: Other event templates remain unchanged**
  - **Given** non-`auditor_start` events such as `sdlc_handshake`, `coder_spawned`, or `uat_start`
  - **When** notifications are formatted
  - **Then** their existing rendered outputs remain unchanged

- **Scenario 4: Regression is locked by tests**
  - **Given** the formatter test suite is executed after the fix
  - **When** the `auditor_start` template is validated with and without `command`
  - **Then** the suite passes only if command visibility is preserved for the populated case and safe fallback is preserved for the empty case

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
The core quality risk is not logic correctness in the Auditor itself. The risk is silent loss of operational visibility caused by template regression.

Therefore the best verification strategy is:
1. **Formatter-focused unit/regression coverage** as the primary guardrail,
2. **no heavy live E2E dependency** for this issue,
3. **strict non-regression checks** for unrelated notification templates.

Recommended testing shape:
- use direct formatter tests as the main proof,
- mock input context dictionaries rather than invoking real Auditor subprocesses,
- only update broader tests if they currently freeze the buggy string as expected behavior.

Quality goal:
- restore explicit command visibility for `auditor_start`,
- preserve safe rendering when `command` is absent,
- keep the fix narrow enough that downstream notification behavior remains stable.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/notification_formatter.py`
- `tests/test_notification_formatter.py`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Frame ISSUE-1173 as a narrow observability regression where `spawn_auditor.py` already passes `command`, but `notification_formatter.py` drops it in the `auditor_start` template.
- **Design Choice**: Fix the formatter instead of changing caller behavior, because the bug is in presentation, not data propagation.
- **Scope Decision**: Keep the PRD intentionally narrow and forbid whole-system notification refactoring so this issue can serve as a clean SDLC smoke test.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`auditor_start` rendered message when `command` is present**:
```text
🚀 [Auditor] Starting PRD audit for: {prd_file}
💻 Command: `{command}`
```

- **`auditor_start` rendered message when `command` is absent**:
```text
🚀 [Auditor] Starting PRD audit for: {prd_file}
```
