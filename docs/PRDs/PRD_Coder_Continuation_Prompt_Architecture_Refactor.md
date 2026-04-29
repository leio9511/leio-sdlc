---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Coder Continuation Prompt Architecture Refactor

## 1. Context & Problem (业务背景与核心痛点)

`leio-sdlc` has already completed the startup-envelope migration for Planner, Reviewer, Auditor, Verifier, and Coder. However, direct runtime evidence from the execution of `PRD_Config_Driven_Multi_CLI_Engine_Integration` exposed a structural flaw in the **Coder continuation loop**.

The issue is not that Coder lacks a revision path. The issue is that the current envelope architecture treats all four Coder lifecycle modes too similarly:
- `initial`
- `revision`
- `revision_bootstrap`
- `system_alert`

Today, all four modes are still assembled through the same high-level `build_coder_startup_packet_and_prompt(...)` → `build_startup_envelope(role="coder", mode=...)` path. That decision is sound for `initial`, but it is wrong or at least over-applied for the continuation modes.

### 1.1 Observed Failure Pattern

During `PR_002_Introduce_Engine_Registry_Config_Contract` under `PRD_Config_Driven_Multi_CLI_Engine_Integration`, the Coder was sent back for revision **multiple times** with materially the same Reviewer finding. The Reviewer feedback was indeed passed into the Coder pipeline, but the Coder repeatedly failed to address it effectively.

The reason is architectural, not merely model-quality noise:

1. **Revision prompts are too close to startup prompts.**
   The current `revision` prompt is still a full startup envelope with a small number of revision-specific clauses inserted. The Reviewer feedback is represented mainly as another file reference rather than as the primary focus of the continuation turn.

2. **Reviewer findings are buried behind reference indirection.**
   The `review_report.json` is passed as `reviewer_feedback` in the `REFERENCE INDEX`, and the Coder is told to read all `required=true, priority=1` references. In practice, this makes the actual rejection reasons much less salient than the repeated startup context.

3. **The architecture confuses bootstrap with continuation.**
   The full startup envelope is appropriate for first-turn context loading (`initial`). It is not automatically appropriate for same-session continuation (`revision`) or operational corrective alerts (`system_alert`). Replaying too much startup context during continuation can dilute the attention budget away from the exact delta that must be fixed.

4. **Session-loss recovery is a distinct mode from first startup.**
   `revision_bootstrap` is not equivalent to `initial`. The codebase and branch already contain prior implementation state; only the conversational session was lost. Treating it like a plain fresh start creates the wrong reasoning posture.

### 1.2 Correct Lifecycle Model

The correct mental model is:

- **A / `initial`** → full bootstrap
- **B / `revision`** → same-session delta continuation
- **C / `revision_bootstrap`** → recovery-shaped full bootstrap
- **D / `system_alert`** → same-session operational delta continuation

This PRD exists to refactor the prompt architecture so those four modes stop sharing the wrong structure.

### 1.3 Explicit Scope Boundary

This PRD is **not** a general redesign of all agents.
It is focused on the Coder only.

Reviewer, Auditor, Planner, and Verifier may have their own future continuation-specific refinements, but they do not currently exhibit the same structural failure mode. Reviewer’s current `--system-alert` path already behaves more like a delta continuation and is therefore not the target of this PRD.

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Preserve `initial` as full envelope startup**
   - `initial` must continue to use the full startup envelope pattern.
   - It must still include PR contract, PRD, playbook, branch/commit/validation constraints, and standard startup artifacts.

2. **Refactor `revision` into a delta continuation prompt**
   - `revision` must no longer reuse the full startup envelope.
   - It must be sent into the existing `.coder_session` as a continuation message.
   - The prompt must inline the Reviewer feedback summary directly into the message body under a dedicated section.
   - The prompt must clearly tell the Coder:
     - this is not a fresh task,
     - existing branch/code state is authoritative,
     - the goal is to address the Reviewer’s findings, not to re-solve the entire PR from scratch.

3. **Refactor `revision_bootstrap` into a recovery-shaped full bootstrap**
   - `revision_bootstrap` must remain a new-session bootstrap because the old session is gone.
   - However, it must not simply reuse the `initial` full envelope.
   - It must be a recovery-specific startup prompt whose highest-priority purpose is to restore context around an already-started task.
   - Reviewer findings must be more prominent than generic startup prose.
   - The prompt must explicitly state that current branch state and current implementation are pre-existing facts, not blank-slate inputs.

4. **Refactor `system_alert` into an operational delta continuation prompt**
   - `system_alert` must no longer use the full startup envelope.
   - If `.coder_session` exists, the alert must be delivered as a direct continuation prompt focused on the exact corrective action.
   - If `.coder_session` does not exist, a new recovery-style system-alert bootstrap may be used, but it must remain tightly scoped to the operational failure.
   - The alert prompt must not restate the entire startup context unless strictly required for recovery.

5. **Inline findings / alert content into the continuation prompt body**
   - For `revision`, the Reviewer’s raw `review_report.json` content must appear directly in the prompt text under a dedicated section rather than being represented only as an indirect file-path reference.
   - For `revision_bootstrap`, the same raw `review_report.json` content must also be inlined prominently in the recovery bootstrap prompt.
   - For `system_alert`, the exact alert text must appear directly in the prompt text in a dedicated section.
   - File-path references may still exist as supporting evidence, but the continuation prompt must not rely on hidden indirection as the primary transport for the required action.

6. **Preserve debug observability**
   - Continuation prompts must still produce debug artifacts.
   - The artifact set must remain mode-specific and non-overwriting.
   - It must be possible to inspect what exact continuation or recovery prompt was sent on each cycle.

7. **Do not break current session continuity behavior**
   - `revision` must continue to reuse the existing `.coder_session` when present.
   - `revision_bootstrap` must continue to create a fresh session when `.coder_session` is missing.
   - `system_alert` must continue to prefer reusing the current session when present.

### 2.2 Non-Functional Requirements

1. Continuation prompts must be *shorter and more action-focused* than startup prompts.
2. The Coder must not need to infer the Reviewer findings from a buried file path alone.
3. The architecture must make the semantic distinction between **startup**, **continuation**, **recovery**, and **operational correction** explicit in code.
4. This refactor must preserve current branch-isolation, git-hygiene, and commit/validation guardrails.

### 2.3 User Stories

- As the Manager, I want revision prompts to clearly carry Reviewer feedback so the Coder stops looping on the same mistake.
- As the Manager, I want session-loss recovery to restore the correct work posture without pretending the task is new.
- As the Auditor, I want debug artifacts that distinguish startup prompts from continuation prompts so I can audit failure loops post-mortem.
- As the Boss, I want the SDLC continuation loop to be reliable enough that a rejected PR actually comes back fixed on the next pass.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Prompt Lifecycle Model

The target lifecycle is:

```text
A. initial
   -> full startup envelope

B. revision
   -> same-session delta continuation prompt

C. revision_bootstrap
   -> recovery-shaped full bootstrap prompt

D. system_alert
   -> same-session operational delta continuation prompt
```

### 3.2 Design Decisions

#### A. `initial` stays on the existing envelope path
No structural change is needed beyond preserving compatibility.

#### B. `revision` becomes a direct continuation prompt
This mode should not call the generic startup envelope builder.
Instead, it should build a compact, explicit revision message that contains:
- a short continuation header,
- the raw `review_report.json` body inlined directly under a dedicated review section,
- a small reminder of branch/commit/validation obligations,
- an instruction to modify the existing implementation rather than restart reasoning from scratch.

This should be sent to the existing session via `send_feedback(session_key, message, ...)`.

#### C. `revision_bootstrap` remains envelope-like, but not initial-like
This mode must still bootstrap a new session, so it cannot be reduced to a pure delta prompt.
However, it must become a **recovery-oriented full prompt**, not a replay of `initial`.
The recovery bootstrap should include:
- PR contract path,
- PRD path,
- current branch name,
- latest commit hash when available,
- prominently inlined raw `review_report.json` content,
- explicit instruction that current branch state is authoritative and this is not a blank-slate task.

#### D. `system_alert` becomes an operational continuation prompt
This mode should be treated like a correction signal, not a task restart.
It should prioritize:
- exact alert text,
- current branch state,
- narrow corrective objective,
- requirement to rerun validation.

If session continuity is intact, send it as a direct continuation prompt.
If continuity is lost, use a compact recovery prompt specialized for system alerts.

### 3.3 Files Expected to Change

- `scripts/spawn_coder.py`
  - split startup vs continuation prompt construction more explicitly
  - separate revision/system-alert prompt builders from startup envelope builder
- `scripts/envelope_assembler.py`
  - either narrow coder envelope usage to startup/recovery contexts only, or add explicit recovery-only rendering helpers
- `playbooks/coder_playbook.md`
  - update lifecycle documentation so it matches the new A/B/C/D model
- tests covering coder continuation and recovery behavior

### 3.4 Architecture Boundary

This PRD does **not** authorize:
- changing Reviewer logic,
- changing orchestrator queue order,
- changing other agents’ continuation paths,
- redesigning the whole SDLC prompt architecture.

It is a focused correction of the Coder continuation semantics.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Initial startup still uses full envelope**
  - **Given** a fresh PR with no `.coder_session`
  - **When** `spawn_coder.py` is invoked without `--feedback-file` or `--system-alert`
  - **Then** the Coder receives the standard full startup envelope and the startup debug artifacts are persisted under `coder_debug/initial/`

- **Scenario 2: Revision uses same-session continuation prompt**
  - **Given** a `.coder_session` exists and the Reviewer has produced `review_report.json`
  - **When** `spawn_coder.py` is invoked with `--feedback-file`
  - **Then** the same session is reused
  - **And** the prompt sent into that session directly contains the raw `review_report.json` body under a prominent dedicated review section
  - **And** the prompt does not replay the full startup envelope

- **Scenario 3: Revision bootstrap restores context after session loss**
  - **Given** no `.coder_session` exists but Reviewer feedback is available
  - **When** `spawn_coder.py` is invoked with `--feedback-file`
  - **Then** a new session is created
  - **And** the startup prompt is recovery-oriented, explicitly stating that existing branch state is authoritative and the task is not a blank-slate startup
  - **And** the raw `review_report.json` body is prominently included in the prompt body

- **Scenario 4: System alert uses operational delta continuation**
  - **Given** a `.coder_session` exists and the orchestrator emits a preflight or git failure
  - **When** `spawn_coder.py` is invoked with `--system-alert`
  - **Then** the same session is reused
  - **And** the prompt directly contains the exact alert text under a dedicated alert section
  - **And** the prompt remains narrowly scoped to corrective action rather than replaying the full startup contract

- **Scenario 5: Continuation artifacts remain auditable**
  - **Given** one or more revision or system-alert cycles occur
  - **When** debug artifacts are inspected
  - **Then** each continuation prompt is persisted under a mode-specific non-overwriting artifact directory
  - **And** a human can inspect what exact continuation or recovery prompt was sent

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Risk
The main risk is that continuation prompts remain too startup-shaped, causing the Coder to repeatedly miss the real delta that must be fixed.

### Testing Strategy
- Use unit/integration tests around `spawn_coder.py` prompt construction.
- Mock `invoke_agent` and verify:
  - same-session continuation for `revision`,
  - new-session bootstrap for `revision_bootstrap`,
  - direct alert messaging for `system_alert`,
  - full envelope retained only for `initial`.
- Assert that revision prompts inline the raw `review_report.json` content.
- Assert that recovery bootstrap prompts inline the raw `review_report.json` content with higher prominence than generic startup prose.
- Assert that system-alert prompts inline the exact alert text.
- Assert that startup/recovery/continuation artifact directories remain distinct and non-overwriting.

### Quality Goal
After this change, a Reviewer rejection must reliably produce a Coder continuation prompt whose primary attention target is the actual review delta. Session continuity and recovery semantics must be explicit and auditable rather than accidentally inherited from the startup-envelope architecture.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_coder.py`
- `scripts/envelope_assembler.py`
- `playbooks/coder_playbook.md`
- Coder continuation / recovery tests

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft based on direct runtime evidence from `PRD_Config_Driven_Multi_CLI_Engine_Integration`, where PR-002 was rejected repeatedly and the Coder failed to effectively act on review feedback.
- **Design correction**: Not all Coder modes should use the same startup-envelope structure. Startup, continuation, recovery, and system correction are distinct lifecycle phases.
- **Explicit lifecycle split**: A = `initial` full bootstrap, B = `revision` delta continuation, C = `revision_bootstrap` recovery-shaped full bootstrap, D = `system_alert` operational delta continuation.
- **Scope discipline**: Reviewer, Auditor, Planner, and Verifier are intentionally out of scope even though future continuation-path reviews may be worthwhile.

---

## 7. Hardcoded Content (硬编码内容)

### Exact prompt section headers

- **Revision prompt feedback section header**:
```text
# REVIEW REPORT JSON
```

- **System alert prompt section header**:
```text
# SYSTEM ALERT YOU MUST FIX
```

- **Recovery bootstrap warning line**:
```text
This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts.
```

### Exact behavioral rule lines

- **Revision continuation rule**:
```text
Do not restart problem-solving from scratch. Modify the existing implementation to satisfy the reviewer findings.
```

- **System-alert continuation rule**:
```text
Do not re-plan the whole PR. Fix the exact operational failure shown below, rerun validation, and continue from the current branch state.
```
