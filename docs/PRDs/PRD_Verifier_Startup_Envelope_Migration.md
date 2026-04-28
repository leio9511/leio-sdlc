---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Verifier Startup Envelope Migration

## 1. Context & Problem (业务背景与核心痛点)

### 1.1 Background

The leio-sdlc startup-envelope migration has already been completed for Planner, Reviewer, Auditor, and Coder. Those four roles are now launched via `envelope_assembler.py` with structured, contract-first startup packets, persisted debug artifacts, and deprecated legacy prompt entries in `config/prompts.json`.

Verifier is now the **last active pipeline agent** still using the old monolithic `build_prompt("verifier", ...)` path. After Verifier is migrated, the entire active SDLC pipeline will be on the envelope architecture.

The remaining two spawn scripts — `spawn_arbitrator.py` and `spawn_manager.py` — are dead code in the current pipeline (neither is called by `orchestrator.py`). They are explicitly out of scope for this migration and will be addressed in a separate cleanup pass.

### 1.2 Current Verifier Architecture

`spawn_verifier.py` is called by the orchestrator at the end of each PRD run as part of User Acceptance Testing:

```text
orchestrator.py → drun(spawn_verifier.py) → build_prompt("verifier") → invoke_agent() → write uat_report.json
```

The `build_prompt("verifier", ...)` call inlines:
- the full verifier playbook path (referenced, not inlined — but the prompt itself is still a legacy template),
- comma-separated PRD file paths,
- output file path,
- JSON schema instructions.

Unlike Coder, the Verifier is a one-shot evaluation agent:
- No persistent session (no `.coder_session` or equivalent)
- No revision loop
- No system-alert path
- No stateful re-entry

This makes the migration structurally similar to Reviewer/Auditor rather than Coder.

### 1.3 Core Pain Points

1. **Last legacy prompt path**: Verifier is the only remaining active agent still routing through `build_prompt()` → `prompts.json`. After this migration, the active pipeline will be fully on envelope architecture.

2. **No startup observability**: The Verifier's startup context (which PRDs it was given, what instructions it received) is not persisted. When `ISSUE-1186` occurred — unauthorized Verifier commits during a UAT run — there was no way to inspect what the Verifier was told to do because no debug artifacts existed.

3. **Inconsistent playbook pattern**: All other active agents now document a "Startup Protocol" section in their playbook defining contract-first priority, required reference reads, and mode awareness. The Verifier playbook has none of this.

4. **Read-Only constraint is informal**: The playbook says "Read-Only" but this is buried in prose. After migration, the execution contract can encode this constraint more prominently.

### 1.4 Relationship to ISSUE-1186

ISSUE-1186 ("SDLC Role Violation: Non-Coder Agent Suspected of Unauthorized Direct-to-Master Code Commits") identified the Verifier as the only suspect in a governance breach. The root cause analysis noted:

> "No session transcript exists — the Verifier's actions during 14:08-14:23 cannot be audited"

This migration **partially mitigates** the observability gap by adding persisted debug artifacts. However, it does **not** add a hard hook-level isolation boundary preventing non-Coder agents from committing — that belongs in a separate enforcement PRD.

### 1.5 Explicitly Not in Scope

- Arbitrator or Manager agent migration (dead code — deferred to cleanup)
- ISSUE-1186 hook-level enforcement (separate PRD)
- Changing the Verifier's UAT output schema (`uat_report.json` format)
- Changing how the orchestrator calls the Verifier (`drun` vs. `invoke_agent`)
- Changing the UAT retry/recovery flow in `orchestrator.py`

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Add `role="verifier"` to `envelope_assembler.py`**
   - `build_startup_envelope(role="verifier", ...)` must produce a structured startup packet with the same top-level shape as other migrated roles: `execution_contract`, `reference_index`, `final_checklist`.
   - The envelope must support comma-separated PRD file paths in the reference index for multi-PRD verification (hotfix chains).

2. **Refactor `spawn_verifier.py` to use envelope instead of `build_prompt()`**
   - Remove production dependency on `build_prompt("verifier", ...)`.
   - Assemble the startup packet via `envelope_assembler.build_startup_envelope(role="verifier", ...)`.
   - Render the prompt from the envelope (path-driven, not body-inlined).
   - The Verifier must receive: PRD file paths (as references, not inlined content), verifier playbook path, and output file path — all conveyed through the envelope's reference index and execution contract.

3. **Add debug artifact persistence**
   - Save `startup_packet.json` and `rendered_prompt.txt` under `{run_dir}/uat_debug/initial/`.
   - Must not overwrite artifacts from earlier pipeline stages (Planner, Reviewer, Coder).

4. **Deprecate legacy prompt entry**
   - Replace the `"verifier"` entry in `config/prompts.json` with the exact deprecation marker:
     ```
     __DEPRECATED__ use envelope_assembler.py — see spawn_verifier.py
     ```

5. **Update `playbooks/verifier_playbook.md`**
   - Add a "Startup Protocol" section defining:
     - Contract-first priority
     - Required reference-read rule
     - Read-Only constraint (emphasized as contractual, not advisory)
     - Output contract (output path from execution contract)
   - Do not remove or rewrite the existing Workflow and Constraints sections.

6. **Preserve backward compatibility**
   - The orchestrator's invocation of `spawn_verifier.py` (`drun` with `--prd-files`, `--workdir`, `--out-file`) must remain unchanged.
   - The Verifier's output format (`uat_report.json` schema) must remain unchanged.
   - Test-mode (`SDLC_TEST_MODE`) mock behavior must be preserved.

### 2.2 Non-Functional Requirements

1. The Verifier startup prompt must be materially shorter than the current monolithic prompt (playbook content should be referenced by path, not inlined).
2. Every UAT run must produce inspectable debug artifacts.
3. The migration must not change the Verifier's behavior contract (same inputs → same outputs).
4. The `envelope_assembler.py` role extension must follow the same pattern as Reviewer/Auditor/Coder — no new architectural patterns.

### 2.3 User Stories

- As the Manager, I want the Verifier startup payload to be contract-first so I can inspect what instructions the Verifier received during a UAT run.
- As the Architect, I want the Verifier playbook to document the new startup protocol so the behavior contract is consistent across all agents.
- As the Auditor, I want persisted Verifier startup artifacts so I can audit UAT runs post-mortem.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Design

The migration upgrades `spawn_verifier.py` from a prompt-concatenation script into an envelope-driven one-shot evaluator:

```text
orchestrator.py → spawn_verifier.py → envelope_assembler.py (role="verifier")
                                    → invoke_agent()
                                    → uat_report.json
                                    → uat_debug/initial/startup_packet.json
                                    → uat_debug/initial/rendered_prompt.txt
```

### 3.2 Envelope Structure for Verifier

`envelope_assembler.py` must support `role="verifier"` with the same top-level shape:

- `execution_contract`: Encodes the read-only constraint, output file path, and required output schema.
- `reference_index`: Lists PRD files (comma-separated, supporting multiple for hotfix chains) and the verifier playbook as `required=true, priority=1` references.
- `final_checklist`: Completion checklist (output file written, read-only constraint respected).

### 3.3 Key Design Decision: Multi-PRD Support

The Verifier takes `--prd-files` as a comma-separated string (e.g., `"PRD_A.md,PRD_B_hotfix.md"`). The envelope's reference index must parse this into individual file references rather than treating it as one opaque string. Each PRD file becomes a separate reference entry, all marked `required=true, priority=1`.

### 3.4 Files to Modify

- `scripts/envelope_assembler.py` — Add `role="verifier"` branch
- `scripts/spawn_verifier.py` — Switch from `build_prompt()` to `envelope_assembler`
- `config/prompts.json` — Deprecate `"verifier"` entry
- `playbooks/verifier_playbook.md` — Add Startup Protocol section

### 3.5 Files Explicitly NOT Authorized for Modification

- `scripts/orchestrator.py` — No changes needed
- `scripts/agent_driver.py` — No changes needed
- `tests/test_spawn_verifier.py` or any test files — Coder may create/modify tests as needed per TDD
- Any other `playbooks/*.md` files
- `config/prompts.json` entries other than `"verifier"`

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** Verifier is launched via envelope for the first time
  - **Given** `spawn_verifier.py` is invoked with `--prd-files "PRD_A.md,PRD_B.md" --workdir /path --out-file uat_report.json`
  - **When** The script assembles the startup packet
  - **Then** A `uat_debug/initial/startup_packet.json` is created containing an execution contract (with read-only constraint and output path) and a reference index listing each PRD file separately with `required=true, priority=1`

- **Scenario 2:** Verifier rendered prompt is contract-first and path-driven
  - **Given** `spawn_verifier.py` is invoked in production mode
  - **When** The startup packet is rendered into the agent prompt
  - **Then** The prompt starts with `# EXECUTION CONTRACT`, includes the verifier playbook and PRD files as paths (not inlined bodies), and does not contain the legacy monolithic prompt text from `prompts.json["verifier"]`

- **Scenario 3:** Legacy prompt entry is deprecated
  - **Given** `config/prompts.json` is read
  - **When** The `"verifier"` key is accessed
  - **Then** Its value equals exactly `__DEPRECATED__ use envelope_assembler.py — see spawn_verifier.py`

- **Scenario 4:** Verifier playbook documents the new startup protocol
  - **Given** `playbooks/verifier_playbook.md` is opened
  - **When** The document is searched for "Startup Protocol"
  - **Then** A section titled "Startup Protocol" exists containing: contract-first priority, required reference-read rule, an emphasized read-only constraint, and output contract

- **Scenario 5:** UAT output behavior is preserved
  - **Given** `spawn_verifier.py` completes successfully
  - **When** `uat_report.json` is inspected
  - **Then** The output schema (`status`, `executive_summary`, `verification_details` with `requirement`/`status`/`evidence`/`comments`) is identical to the pre-migration format

- **Scenario 6:** Test-mode backward compatibility is preserved
  - **Given** `SDLC_TEST_MODE=true` is set
  - **When** `spawn_verifier.py` is invoked
  - **Then** The mock result is written to `uat_report.json` and the task string is logged to `tests/verifier_task_string.log` (same behavior as pre-migration)

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk

The primary risk is breaking the UAT pipeline — if the Verifier produces a differently-shaped `uat_report.json` or fails to write the output file at all, the orchestrator's UAT retry loop will fail and the pipeline will be blocked.

### Mocking Strategy

- The Verifier agent itself (LLM call) must be mocked. The envelope assembly and artifact persistence are what need validation — not the LLM's UAT evaluation.
- Mock the `invoke_agent()` call to return success without actually calling GPT.
- Test envelope shape, reference index correctness, and artifact file creation in isolation.

### Test Coverage

- **Unit-level**: Envelope packet shape validation (same style as `test_coder_startup_envelope.py`).
- **Integration-level**: `spawn_verifier.py` end-to-end in test mode producing the correct debug artifacts.
- **Regression**: Existing verifier-related tests must continue to pass.
- **No live LLM E2E needed**: The Verifier's behavior with a real LLM is already validated by the existing UAT pipeline.

## 6. Framework Modifications (框架防篡改声明)

- `scripts/envelope_assembler.py` — Authorized for adding `role="verifier"` branch
- `scripts/spawn_verifier.py` — Authorized for switching from `build_prompt()` to envelope
- `config/prompts.json` — Authorized for deprecating the `"verifier"` entry only
- `playbooks/verifier_playbook.md` — Authorized for adding a "Startup Protocol" section only

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft based on completed Coder Envelope Migration pattern. Verifier is the simplest remaining migration — one-shot evaluator with no session/state/revision complexity. Migration follows the same three-piece pattern: envelope_assembler extension, spawn script refactor, prompt deprecation.
- **Design trade-off**: Multi-PRD support via comma-separated `--prd-files` is retained rather than converting to a list argument, to avoid changing the orchestrator's invocation shape. The envelope's reference index splits the comma-separated string internally for structured representation.
- **ISSUE-1186 relationship**: This migration adds observability (debug artifacts) but not hard isolation. The hook-level enforcement required by ISSUE-1186 is explicitly deferred to a separate PRD.

---

## 7. Hardcoded Content (硬编码内容)

### Deprecation Marker

- **For `config/prompts.json` `"verifier"` entry (Replace entire value)**:
  `__DEPRECATED__ use envelope_assembler.py — see spawn_verifier.py`

### Playbook Addition

- **For `playbooks/verifier_playbook.md` (Insert after Constraints section)**:
```markdown
## Startup Protocol

You are started via a structured execution envelope.

- **Contract-First Priority**: The execution contract in your startup prompt is authoritative over general prose. If any instruction in this playbook appears to conflict with the execution contract, the execution contract takes precedence.
- **Required Reference-Read Rule**: Before beginning verification, you MUST read all references in the REFERENCE INDEX marked `required=true` and `priority=1`. This includes every PRD file listed in the reference index.
- **Read-Only (EMPHASIZED)**: You are an evaluation agent. The execution contract enforces read-only mode. You MUST NOT modify, create, or delete any file in the workspace except the final `uat_report.json` artifact. This is a contractual constraint derived from the execution contract, not an optional suggestion.
- **Output Contract**: Write your UAT evaluation JSON to the exact path specified in the execution contract's `output_file` field. The required JSON schema is defined in the execution contract.
```
