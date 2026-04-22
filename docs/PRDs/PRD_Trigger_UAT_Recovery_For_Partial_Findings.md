---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Trigger_UAT_Recovery_For_Partial_Findings

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` currently supports a State 6 UAT recovery path in `orchestrator.py`, but its trigger condition is too narrow. When the UAT verifier returns `status = NEEDS_FIX`, the orchestrator only auto-invokes planner recovery if `verification_details` contains items marked `MISSING`. If the UAT report instead contains actionable findings marked `PARTIAL`, the pipeline does not invoke `spawn_planner.py --replan-uat-failures`; it falls through to the manager handoff path and asks for manual hotfix/redo judgment.

This creates a self-healing blind spot. In practice, `PARTIAL` often means the feature is implemented incompletely but still concretely enough for an automated hotfix plan. The pipeline therefore already knows what is wrong, but refuses to re-enter the planner loop because the status label is not exactly `MISSING`.

Recent production evidence already exposed this failure mode. A UAT report returned `NEEDS_FIX` with actionable `PARTIAL` findings for runtime boundary enforcement and environment-agnostic handoff hints. The system should have generated a planner hotfix PR automatically, but it instead halted for manager intervention. This breaks the intended self-healing behavior of the SDLC engine and forces unnecessary human routing.

This PRD intentionally adopts the smallest safe fix, referred to in discussion as “方案 A”: treat both `MISSING` and `PARTIAL` as planner-recoverable findings in State 6. This avoids a larger semantic redesign of the verifier schema or recovery policy while restoring the missing automated hotfix loop immediately.

## 2. Requirements & User Stories (需求定义)
1. **Expand State 6 Recovery Trigger**
   - When `uat_status == NEEDS_FIX`, the orchestrator must trigger planner-based recovery if `verification_details` contains actionable findings with status `MISSING` or `PARTIAL`.
   - Recovery must continue using the existing `spawn_planner.py --replan-uat-failures <uat_report.json>` path.

2. **Preserve Existing Recovery Guardrails**
   - Existing retry caps, UAT recovery counters, and circuit-breaker behavior must remain intact.
   - This PRD must not weaken safety boundaries or create infinite recovery loops.

3. **Correct Manager Handoff Language**
   - If the pipeline still falls through to manager handoff for a `NEEDS_FIX` result, the handoff text must no longer incorrectly instruct the manager to summarize only “MISSING” items.
   - The wording must align with the broader reality that failures may be expressed as `PARTIAL`.

4. **Scope Control**
   - This PRD is strictly limited to the minimal State 6 trigger fix.
   - It must not redesign verifier schemas, introduce new status taxonomies, or attempt a general “actionable findings” framework in this iteration.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
The implementation should remain narrowly focused on the State 6 UAT recovery branch in `scripts/orchestrator.py`.

### Target Files
- `scripts/orchestrator.py`
- Any directly relevant orchestrator State 6 tests covering UAT recovery behavior and manager handoff wording

### Chosen Strategy (方案 A)
1. **Minimal Trigger Broadening**
   - Update the current UAT recovery filter so planner recovery triggers when `verification_details` includes items whose status is either `MISSING` or `PARTIAL`.
   - Keep the existing `NEEDS_FIX` gating and current planner invocation path.

2. **No Schema Redesign**
   - Do not introduce new UAT schema fields like `actionability`, `recovery_recommendation`, or similar abstractions in this PR.
   - Those may be considered later if needed, but are explicitly out of scope for this fix.

3. **Manager Handoff Consistency Fix**
   - Update the fallback manager handoff message so it no longer hardcodes “summarize the MISSING items.”
   - The wording should reflect unmet findings more generically, so it remains correct when the UAT report contains `PARTIAL`-only failures.

4. **Restraint Principle**
   - This PR is a tactical repair to restore the self-healing loop.
   - It must avoid broader refactors in the orchestrator state machine.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: UAT recovery triggers on PARTIAL findings**
  - **Given** the UAT verifier produces `status = NEEDS_FIX`
  - **And** the `verification_details` contain one or more items with status `PARTIAL`
  - **When** the orchestrator processes the UAT report in State 6
  - **Then** it invokes the planner recovery path using `spawn_planner.py --replan-uat-failures ...`
  - **And** it does not fall through directly to manager handoff only because no item is labeled `MISSING`

- **Scenario 2: Existing MISSING behavior still works**
  - **Given** the UAT verifier produces `status = NEEDS_FIX`
  - **And** the `verification_details` contain one or more items with status `MISSING`
  - **When** the orchestrator processes the report
  - **Then** it continues to invoke the existing planner recovery flow as before

- **Scenario 3: Clean pass behavior is unchanged**
  - **Given** the UAT verifier produces `status = PASS`
  - **When** the orchestrator processes the UAT report
  - **Then** it does not trigger planner recovery
  - **And** it proceeds through the success handoff path unchanged

- **Scenario 4: Manager handoff wording stays accurate**
  - **Given** the UAT verifier produces `status = NEEDS_FIX`
  - **And** the pipeline reaches a manager-intervention branch
  - **When** the orchestrator emits the manager handoff instruction
  - **Then** the message does not incorrectly refer only to “MISSING” items
  - **And** the wording remains correct for `PARTIAL`-only failure reports

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
The main quality risk is that a narrow change to the recovery trigger could unintentionally alter other State 6 branches or recovery caps. A second risk is that the planner trigger is fixed but the human-facing handoff text remains semantically stale.

### Verification Strategy
1. **Deterministic Unit/Integration Coverage (CI-safe)**
   - Add or update orchestrator tests that inject synthetic `uat_report.json` payloads.
   - At minimum, include:
     - a `NEEDS_FIX` + `PARTIAL` case that must trigger planner recovery,
     - a `NEEDS_FIX` + `MISSING` case that still triggers recovery,
     - a `PASS` case that does not trigger recovery.

2. **Message/Handoff Coverage**
   - Add a test or assertion verifying that the manager handoff text no longer hardcodes “MISSING” in the fallback branch.

3. **No Live-LLM Requirement**
   - This fix is deterministic orchestrator control logic and does not require live-LLM validation.
   - Mocked or synthetic `uat_report.json` inputs are sufficient and preferred.

### Quality Goal
The pipeline should recover automatically from UAT reports that contain actionable `PARTIAL` findings, restoring the intended State 6 self-healing loop without broadening scope beyond the minimal hotfix.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- Any orchestrator tests needed to verify State 6 UAT recovery and handoff wording

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft proposed a broader semantic redesign of UAT recovery toward “actionable findings,” independent of exact status labels.
- **Boss Direction**: Chosen implementation is the narrower “方案 A” path, explicitly broadening the trigger from `MISSING` to `MISSING or PARTIAL` without redesigning the verifier schema.
- **Design Rationale**: This restores the missing self-healing behavior quickly while keeping the blast radius small and avoiding a larger verifier/orchestrator contract rewrite.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`manager_uat_fallback_summary_text`**:
```text
Read uat_report.json, summarize the unmet findings to the Boss, and ask whether to append a hotfix or redo.
```
