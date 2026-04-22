---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Refine_Coder_Revision_Prompt

## 1. Context & Problem (业务背景与核心痛点)
The current `leio-sdlc` revision loop relies on a very thin `coder_revision` prompt in `config/prompts.json`. It wraps the reviewer JSON and appends a short instruction telling the Coder to address the feedback. This has proven sufficient in Gemini-driven runs, but it is not robust across engines.

Recent production evidence from the OpenClaw engine using GPT-5.4 showed that reviewer feedback for PR-001 was successfully delivered into the persistent coder session, yet the Coder often responded with acknowledgment-only messages such as “I have read the instructions” instead of performing durable corrective work. The same long-lived session also accumulated `SYSTEM ALERT`, dirty-workspace/preflight notifications, and at least one empty-diff review cycle, increasing context noise.

The current diagnosis is that the primary failure mode is not feedback delivery or session-id routing. It is a weak revision prompt interacting badly with long-lived noisy revision loops. As a result, the pipeline can degrade into “read-and-acknowledge” behavior instead of continuing the intended code-fix workflow.

This is a reliability problem in the SDLC engine itself. The prompt contract for revision loops must be made more explicit and action-constraining so that the Coder is guided into execution, not passive acknowledgment, across both Gemini and OpenClaw-backed model runs.

## 2. Requirements & User Stories (需求定义)
1. **Action-Oriented Revision Prompt**
   - Strengthen `coder_revision` so it clearly frames revision handling as an execution task rather than an acknowledgment task.
   - The prompt must explicitly require the Coder to:
     1. extract reviewer findings,
     2. map findings to concrete files,
     3. modify the codebase,
     4. run relevant tests or preflight,
     5. commit explicit files,
     6. leave the workspace clean.

2. **Explicit Anti-Acknowledgment Guardrail**
   - The prompt must explicitly forbid acknowledgment-only responses such as “I have read the instructions.”
   - The prompt must define that failing to make code changes after revision feedback counts as task failure.

3. **System Alert Prompt Hardening**
   - `coder_system_alert` must also be strengthened so system alerts do not read like passive context updates.
   - It must continue to direct the Coder toward concrete remediation actions (fix code / fix dirty workspace / rerun checks / commit explicit files).

4. **Scope Restraint**
   - This PRD is scoped only to prompt-contract hardening for revision/system-alert flows.
   - It must not expand into session lifecycle redesign, coder session reset policy, or orchestrator state-machine redesign.

5. **Cross-Engine Robustness**
   - The strengthened prompts should be written to reduce ambiguity across both Gemini and OpenClaw-backed model runs, with particular focus on GPT-5.4 reliability in long revision loops.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Primary Target File**: `config/prompts.json`
- **Prompt Surface to Modify**:
  - `coder_revision`
  - `coder_system_alert`

### Technical Strategy
1. **Revise Prompt Framing**
   - Replace the current minimal `coder_revision` phrasing with a structured execution contract.
   - The revised prompt should explicitly state that the revision loop is an execution task, not a read/acknowledgment step.

2. **Action Checklist Structure**
   - The prompt should enumerate required actions in order, so the model sees a concrete procedural contract instead of an abstract instruction.
   - This checklist must remain concise enough to avoid unnecessary token bloat, while being strict enough to constrain execution behavior.

3. **Failure Semantics**
   - The prompt should state that no-code-change responses after revision feedback are invalid.
   - This is not meant to enforce runtime behavior by code, but to strengthen the model-facing contract.

4. **Test Strategy Integration**
   - This issue cannot rely only on pure unit logic because the ultimate risk is model behavior.
   - Therefore verification must be layered:
     - **Layer 1, CI-safe**: prompt rendering and content assertions.
     - **Layer 2, mocked flow**: revision/system-alert injection tests proving the hardened prompt is actually propagated through the SDLC chain.
     - **Layer 3, live-LLM validation**: a targeted real-model canary or live E2E to validate that the revised prompt reduces acknowledgment-only behavior under realistic revision-loop conditions.

5. **Scope Boundary**
   - Do not redesign session reuse, reset policy, or orchestrator yellow-path logic in this PRD.
   - If prompt hardening proves insufficient, those concerns should be handled in a follow-up PRD/issue.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Revision prompt is clearly action-oriented**
  - **Given** the SDLC engine renders `coder_revision` with reviewer feedback content
  - **When** the final prompt text is inspected
  - **Then** it explicitly describes the task as an execution task rather than an acknowledgment task
  - **And** it explicitly requires code modification, testing/preflight, explicit commit, and a clean workspace

- **Scenario 2: Acknowledgment-only behavior is explicitly prohibited**
  - **Given** the SDLC engine renders `coder_revision`
  - **When** the prompt is inspected
  - **Then** it explicitly forbids acknowledgment-only responses such as “I have read the instructions”
  - **And** it states that failing to make code changes after revision feedback is considered task failure

- **Scenario 3: System alert prompt remains action-constraining**
  - **Given** the SDLC engine renders `coder_system_alert` for a dirty workspace or preflight failure
  - **When** the final prompt text is inspected
  - **Then** it clearly instructs the Coder to take corrective action on the codebase or Git state rather than treating the alert as passive context

- **Scenario 4: Hardened prompts are actually injected into the coder path**
  - **Given** a mocked revision loop or mocked system-alert loop
  - **When** the SDLC engine routes feedback to the Coder
  - **Then** the rendered prompt delivered through the spawn/agent-driver chain contains the strengthened prompt contract instead of the legacy thin wording

- **Scenario 5: Live model validation demonstrates improved revision handling**
  - **Given** a controlled live-LLM revision scenario using the target engine/model family
  - **When** revision feedback is delivered through the real SDLC coder path
  - **Then** the Coder performs code-oriented follow-up behavior rather than replying with acknowledgment-only text under the tested scenario

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
The main risk is not prompt rendering correctness, but behavioral ambiguity under real LLM execution, especially in long-lived revision sessions with mixed signals.

### Verification Strategy
1. **Prompt Contract Tests (CI-safe)**
   - Add direct assertions against rendered prompt text to ensure the hardened wording remains present.
   - These tests should be deterministic and must run in normal CI.

2. **Mocked Revision-Flow Tests (CI-safe)**
   - Add mocked SDLC tests that validate `coder_revision` and `coder_system_alert` are injected through the expected chain.
   - These tests should verify prompt propagation and guard against accidental regression to the thin legacy wording.

3. **Live-LLM Validation (Non-blocking / nightly / release-gate style)**
   - Add or extend a live-LLM test for a controlled revision-loop scenario.
   - This test should not be a hard gate on every PR due to network cost, provider variability, and non-determinism.
   - It should instead act as a canary/nightly/release validation layer for prompt-behavior regression.

### Quality Goal
The system should become meaningfully more robust against acknowledgment-only revision responses across engines, with CI covering prompt integrity and mocked propagation, and live validation covering real behavioral improvement.

## 6. Framework Modifications (框架防篡改声明)
- `config/prompts.json`
- Any lightweight SDLC test files needed to verify prompt rendering and mocked revision/system-alert propagation
- Any live-LLM test harness file explicitly created or updated for revision-loop validation

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial PRD drafted to address `ISSUE-1170` by hardening `coder_revision` and `coder_system_alert`.
- **Design Rationale**: Prompt hardening is intentionally isolated from broader session-hygiene redesign so that the first intervention remains small, measurable, and attributable.
- **Testing Trade-off**: Pure CI cannot prove real-model behavior; therefore the design explicitly uses layered verification with CI-safe prompt tests plus separate live-LLM validation.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`coder_revision_required_clause`**:
```text
This is an execution task, not an acknowledgment task.
```

- **`coder_revision_forbidden_ack_clause`**:
```text
You MUST NOT respond with only an acknowledgment such as "I have read the instructions".
```

- **`coder_revision_failure_clause`**:
```text
If you do not make code changes after revision feedback, you have failed the task.
```

- **`coder_revision_required_actions`**:
```text
You MUST do all of the following in this turn:
1. Extract the reviewer findings and identify the concrete files that must change.
2. Modify the codebase to address every finding.
3. Run the relevant tests and/or preflight until green.
4. Commit the required files explicitly.
5. Leave the workspace clean.
```

- **`coder_system_alert_execution_clause`**:
```text
This alert requires corrective action, not acknowledgment only.
```
