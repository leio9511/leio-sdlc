---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Auditor Startup Envelope Refactor

## 1. Context & Problem (业务背景与核心痛点)

### 1.1 Background

ISSUE-1183 identified a systemic startup-prompt architecture failure across the SDLC pipeline: long monolithic prompts cause concrete execution instructions to be buried hundreds of lines after the model has already formed a high-level task interpretation. The fix was validated on the Planner as a **Planner-first, architecturally complete** refactor, establishing a reusable three-layer startup envelope pattern.

The PRD for ISSUE-1183 explicitly mandated forward-compatibility: the resulting architecture must be role-agnostic and support migration of Auditor, Reviewer, Coder, and Verifier under separate follow-up PRDs. This PRD delivers the second migration target: the **Auditor**.

### 1.2 Current Auditor Startup Architecture

The current `spawn_auditor.py` flow builds one oversized startup prompt by directly inlining:

- the Auditor playbook (full methodology text),
- the full PRD body being audited,
- the PR contract template (for review-context awareness),
- the structural/output format instructions,
- and the mechanical execution contract (output path, JSON schema, no-YOLO rule).

This is the exact same monolithic pattern that ISSUE-1183 diagnosed as fragile. The concrete audit requirements (JSON output contract, mandatory Section 7 check, no-autofix rule) appear in the middle of a long prompt competing with the full PRD body and playbook text.

### 1.3 Why Auditor is the Ideal Second Target

The Auditor is significantly simpler than the Planner, Coder, or Reviewer:

| Dimension | Auditor | Planner |
|---|---|---|
| Output | Single JSON verdict (approx. 1KB) | Multiple PR contract files (complex) |
| Statefulness | Stateless, one-shot read-only | Stateful, multi-mode (plan/slice/replan) |
| Artifact generation | None (writes verdict only) | Creates dependency-ordered PR set |
| Entry modes | 2 (standard audit, re-audit) | 3 (plan, slice, replan) |
| Context needed | PRD + playbook + output schema | PRD + playbook + template + job config |

This simplicity makes the Auditor the lowest-risk follow-up migration, while still validating that the three-layer envelope pattern generalizes beyond the Planner.

### 1.4 Pain Points

1. **Instruction burial**: The JSON output contract (`{"status": "APPROVED"|"REJECTED", "comments": "..."}`) and the no-autofix rule appear deep inside a long prompt, competing with the inlined PRD for attention.
2. **Redundant content inlining**: The full PRD body and full playbook text are concatenated into the prompt even though the auditor needs to *read* them, not have them pre-loaded. This wastes context window and buries priority instructions.
3. **No structured startup packet**: Unlike the refactored Planner, the Auditor startup has no durable, inspectable startup packet persisted in the run directory, making post-mortem debugging dependent on inference.
4. **Hardcoded template validation is mixed with LLM prompt content**: The structural section-missing check and the Section 7 anti-hallucination check run in Python before the LLM prompt, but the *wording* of those checks is mixed with the prompt assembly, creating an unclear boundary between deterministic validation and LLM reasoning.

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Auditor-only scope for this PRD**
   - This PRD must modify only the Auditor startup path in `spawn_auditor.py`.
   - Reviewer, Coder, Verifier, and Arbitrator prompt/playbook refactors are explicitly out of scope.
   - The implementation must follow the same three-layer envelope pattern validated by ISSUE-1183.

2. **Replace the monolithic Auditor startup prompt with a startup envelope**
   - The Auditor startup payload must be restructured into exactly three ordered layers:
     1. `execution_contract`
     2. `reference_index`
     3. `final_checklist`
   - The first visible startup content for the Auditor must be the execution contract, not the PRD body, not the playbook.

3. **No `task brief` in Phase 1**
   - The Auditor startup envelope must not include a `task_brief` field or any equivalent manually-authored summary layer.
   - Same anti-distortion guardrail as ISSUE-1183: the refactor must improve context structure without introducing summary-bias failure modes.

4. **Reference-index-driven progressive disclosure**
   - The Auditor startup payload must no longer inline the full contents of:
     - `prd_content`
     - `playbook_content`
     - `template_content` (if referenced)
   - Instead, provide a structured `reference_index` containing absolute paths and minimal metadata.
   - The Auditor must be instructed to use native file reads to load those references on demand.

5. **Auditor-specific mandatory references**
   - For the standard audit path, the `reference_index` must include these required `priority=1` references:
     - the authoritative PRD being audited,
     - the Auditor playbook (`config/auditor_playbook.md`),
     - the JSON output schema / contract definition.
   - Before producing a verdict, the Auditor must be instructed to read all required references with `priority=1`.

6. **Mechanical execution contract must be front-loaded and explicit**
   - The Auditor execution contract must explicitly state all of the following before the reference index:
     - the locked `workdir`,
     - the exact PRD file path being audited,
     - the JSON output format (exact schema: `{"status": "APPROVED"|"REJECTED", "comments": "..."}`),
     - the output verdict file path (if saving to disk),
     - the Mandatory Read Rule: all `priority=1` references must be read with native file tools before producing the verdict,
     - the Anti-YOLO Rule: the Auditor must never auto-correct the PRD, only evaluate and report findings.

7. **Preserve current Auditor business behavior while changing startup architecture**
   - The Auditor must still evaluate structural completeness (Section 7 presence, required sections).
   - The Auditor must still produce a JSON verdict with `status` and `comments`.
   - The Auditor must still support the STDIO output for Manager capture.
   - The refactor must preserve the existing exit-code policy: `exit(0)` for both APPROVED and REJECTED (anti-YOLO guardrail from PRD_Fix_Auditor_YOLO).
   - The deterministic pre-flight template validation (missing sections check, Section 7 check) must remain as Python code in `spawn_auditor.py`, NOT be moved into the LLM prompt. Only the *full-document qualitative audit* should use the LLM envelope.

8. **All Auditor entry paths must use the same startup-envelope architecture**
   - The two Auditor runtime entry modes must use the same envelope:
     1. standard PRD audit,
     2. re-audit (after PRD has been revised per previous rejection).
   - These modes may differ in contract wording and reference entries, but must not use separate legacy prompt assembly.

9. **Auditor observability artifacts are mandatory**
   - Each Auditor invocation must persist the structured startup packet / envelope data inside the active run directory.
   - At minimum: `auditor_debug/startup_packet.json` containing the assembled envelope.
   - This enables debugging from hard evidence rather than inference when a future audit produces unexpected verdicts.

10. **Forward-compatibility must be maintained**
    - This PRD's three-layer envelope must remain role-agnostic.
    - The architecture must not introduce Auditor-specific assumptions that would block later Coder, Reviewer, or Verifier migration.
    - The startup envelope helper (envelope assembly / rendering) should be reused or generalized, not rewritten per role.

### 2.2 Non-Functional Requirements

1. The new Auditor startup prompt must be materially shorter than the current monolithic prompt.
2. The design must reduce long-context instruction burying without depending on a manually-authored task summary.
3. The solution must be deterministic and auditable: startup packet, rendered prompt, and resolved paths must be inspectable after the run.
4. The solution must preserve all existing safety guardrails: Section 7 check, no-YOLO rule, structural validation.
5. The resulting envelope helper must be structured so future roles can reuse it without rewriting prompt assembly from scratch.

### 2.3 Explicit Non-Goals

- redesigning the Reviewer, Coder, or Verifier startup prompts,
- rewriting the Auditor playbook in this PRD,
- changing the deterministic pre-flight validation logic in `spawn_auditor.py`,
- changing the exit-code policy,
- introducing a task-summary or task-brief layer,
- broad SDLC orchestrator state-machine changes,
- changing the `invoke_agent()` or temp-file transport mechanism.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Core design principle

The Auditor startup path must follow the same architectural shift as ISSUE-1183: **contract-first progressive disclosure**.

The startup payload should:
1. put the highest-priority mechanical contract first (what to audit, what format to output, critical constraints),
2. provide a role-specific reference index for mandatory reads,
3. finish with a short checklist repeating the critical contract,
4. rely on on-demand reading of long materials through native file tools.

### 3.2 Auditor startup envelope structure

The Auditor startup architecture must be built around a structured startup envelope with exactly these top-level layers:

**Layer 1: `execution_contract`**
- Role identity: Auditor
- Locked workdir
- Exact PRD file path being audited
- Exact output verdict file path (the `.auditor_verdict.json` file to write)
- JSON output schema contract (exact: `{"status": "APPROVED"|"REJECTED", "comments": "..."}`)
- Mandatory Read Rule: all `priority=1` references must be read before producing verdict
- Anti-YOLO Rule: evaluate only, never modify the PRD
- No-file-modification rule: the Auditor must not modify any project files except writing the verdict file

**Layer 2: `reference_index`**
- Structured list of absolute-path references
- Each reference includes only minimal routing metadata:
  - `id`: unique identifier
  - `kind`: what type of document (prd, playbook, schema)
  - `path`: absolute filesystem path
  - `required`: boolean
  - `priority`: numeric (1 = must read before producing output)
  - `purpose`: short mechanical purpose, not a business summary
- No business summary layer, no full document bodies inline

**Layer 3: `final_checklist`**
- Short repeated checklist of the highest-risk constraints:
  - exact PRD path
  - exact verdict output path
  - JSON output format constraint
  - Mandatory Read Rule
  - Anti-YOLO Rule (evaluate only, never modify)

### 3.3 Deterministic pre-flight vs LLM audit boundary

This is a key architectural distinction from the Planner refactor.

The Auditor performs two logically distinct checks:
1. **Deterministic pre-flight** (Python code in `spawn_auditor.py`):
   - Structural section check (required sections exist in PRD)
   - Section 7 anti-hallucination check
   - These must remain in Python code, NOT in the LLM envelope

2. **Qualitative LLM audit** (envelope-driven):
   - Full-document content review
   - Architectural consistency evaluation
   - Blast radius and risk assessment
   - This moves from monolithic prompt to envelope assembly

The deterministic checks run first and exit early on failure. Only if they pass does the envelope-driven LLM audit proceed.

### 3.4 Auditor prompt rendering strategy

The rendered Auditor prompt sent through `invoke_agent()` must become a short launcher prompt derived from the startup envelope.

It must:
- present the execution contract first,
- present the reference index second,
- present the final checklist last,
- instruct the Auditor to read all required `priority=1` references before producing a verdict,
- avoid embedding the raw full contents of the PRD, playbook, or template directly into the first-turn prompt.

### 3.5 Envelope assembly helper

The logic to build the three-layer envelope must reside in a reusable helper, not inlined in `spawn_auditor.py`. A new module `scripts/envelope_assembler.py` should provide:

- `build_startup_envelope(role, workdir, references, contract, mode)` → `dict`
- `render_envelope_to_prompt(envelope)` → `str` (the short launcher prompt)

This helper must be role-agnostic. The role-specific content (contract text, reference list) is injected through parameters, not hardcoded in the helper.

The same helper should in principle be usable by future role migrations (Reviewer, Coder, Verifier) without modification.

### 3.6 Auditor entry-mode unification

This PRD treats the Auditor as one role with two task modes using the same envelope architecture:

1. **Standard audit**: Evaluate a new PRD for structural and qualitative soundness.
2. **Re-audit**: Re-evaluate a PRD that was previously REJECTED and has since been revised.

Allowed differences per mode:
- task sentence inside `execution_contract`,
- mode-specific required references (re-audit may include the previous rejection report as a required reference),
- mode-specific checklist items.

Disallowed difference:
- falling back to a separate legacy giant prompt that directly inlines long reference bodies.

### 3.7 Observability design

Each Auditor invocation must persist startup evidence inside the active run directory.

Recommended artifact set:
- `auditor_debug/startup_packet.json` — the structured envelope before rendering
- `auditor_debug/rendered_prompt.txt` — the actual prompt string sent to the LLM
- `auditor_debug/auditor_verdict.json` — the final JSON verdict (mirrored from the canonical verdict path)

These artifacts must be deterministic (re-run with same inputs produces same artifacts) and inspectable after the run.

### 3.8 Pipeline integration

The `spawn_auditor.py` script must be modified to:
1. Run deterministic pre-flight validation (unchanged, Python code).
2. If pre-flight passes, call the envelope assembler to build the startup envelope.
3. Write `startup_packet.json` and `rendered_prompt.txt` to the run directory.
4. Pass the rendered prompt to `invoke_agent()`.
5. Capture the JSON verdict output.
6. Persist the verdict to `auditor_debug/auditor_verdict.json` and the canonical verdict path.
7. Send notifications and produce the MANAGER action-required message (unchanged).

The ignition handshake, channel notification, and exit-code policy must remain unchanged.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Standard audit produces envelope-driven prompt**
  - **Given** a valid PRD exists at a known path
  - **When** `spawn_auditor.py --prd-file <path>` runs
  - **Then** the LLM prompt is assembled from a three-layer envelope (execution_contract, reference_index, final_checklist), not from a monolithic concatenation of PRD + playbook + template bodies

- **Scenario 2: No full PRD body in first-turn prompt**
  - **Given** a standard audit invocation
  - **When** the rendered prompt is inspected in `auditor_debug/rendered_prompt.txt`
  - **Then** the prompt must NOT contain the full inline text of the PRD body, the playbook body, or the template body

- **Scenario 3: Mandatory reference index present**
  - **Given** a standard audit invocation
  - **When** the startup packet is inspected in `auditor_debug/startup_packet.json`
  - **Then** the packet must contain a `reference_index` with at least `priority=1` entries for the PRD path, the Auditor playbook path, and the JSON output schema

- **Scenario 4: Execution contract is front-loaded**
  - **Given** a standard audit invocation
  - **When** the rendered prompt is inspected
  - **Then** the first substantive content must be the `execution_contract`, not the reference index, not the checklist, and not any reference body

- **Scenario 5: Deterministic pre-flight unchanged**
  - **Given** a PRD missing required sections or Section 7
  - **When** `spawn_auditor.py` runs
  - **Then** the Python pre-flight check must still reject the PRD before any LLM invocation, with the same error message format

- **Scenario 6: Startup artifacts persisted**
  - **Given** a successful standard audit
  - **When** the run directory is inspected
  - **Then** `auditor_debug/startup_packet.json`, `auditor_debug/rendered_prompt.txt`, and `auditor_debug/auditor_verdict.json` must exist and contain valid content

- **Scenario 7: Anti-YOLO exit code preserved**
  - **Given** a REJECTED audit verdict
  - **When** the script exits
  - **Then** the exit code must be 0 (not 1), preserving the anti-YOLO guardrail

- **Scenario 8: Envelope helper is role-agnostic**
  - **Given** the `scripts/envelope_assembler.py` module
  - **When** inspected
  - **Then** it must not contain Auditor-specific hardcoded strings or role-specific branching; role-specific content must be injected via parameters

- **Scenario 9: Re-audit mode produces mode-specific envelope**
  - **Given** a re-audit invocation (PRD has a prior rejection report)
  - **When** the startup packet is inspected
  - **Then** the `reference_index` must include the previous rejection report as a `priority=1` reference, and the execution contract must reflect re-audit mode wording

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
The primary risk is that the new envelope architecture inadvertently changes the Auditor's qualitative judgment behavior (false approvals or false rejections) by restructuring the prompt, even though all the same information is ultimately available through on-demand reading.

### Mitigation Strategy

1. **Artifact-based validation (primary)**: The most critical test is deterministic inspection of startup artifacts, not running the LLM. Tests must verify:
   - the rendered prompt does NOT contain inlined reference bodies,
   - the execution contract appears before reference index,
   - the startup packet is structurally valid,
   - the envelope helper produces correct output for Auditor parameters.
   
2. **Promptdiff testing**: A test snapshot the rendered prompt from a before/after comparison to prove the new envelope is structurally different (no inlined bodies) while preserving the same mechanical constraints.

3. **Mocked LLM testing**: Run `SDLC_TEST_MODE=true` with `MOCK_AUDIT_RESULT=APPROVED`/`REJECTED` to verify the full pipeline path (pre-flight -> envelope assembly -> prompt render -> verdict capture -> notification) doesn't break.

4. **No live LLM comparison test**: This PRD does not require a live E2E test comparing before/after auditor verdicts on the same PRD, as qualitative LLM behavior is inherently non-deterministic. The test strategy focuses on structural and deterministic properties.

### Test Types

| Test Type | Scope | Required |
|---|---|---|
| Unit tests | `envelope_assembler.py` — envelope structure, rendering, parameter injection | Yes |
| Integration tests | `spawn_auditor.py` — pre-flight + envelope assembly + verdict capture pipeline | Yes |
| E2E mocked tests | Full `spawn_auditor.py` run with `SDLC_TEST_MODE=true` | Yes |
| Artifact snapshot tests | `auditor_debug/*` files are created with correct structure | Yes |
| Live LLM tests | Qualitative behavior comparison | No (intentionally excluded) |

## 6. Framework Modifications (框架防篡改声明)

- `scripts/spawn_auditor.py` — **Modified**: Refactor prompt assembly to use envelope assembler; preserve deterministic pre-flight, notification, and exit logic
- `scripts/envelope_assembler.py` — **New File**: Role-agnostic startup envelope builder and prompt renderer
- `scripts/agent_driver.py` — **Modified** (minor): The `build_prompt("auditor", ...)` call path may need adjustment if the envelope replaces the current prompt-building path
- `config/prompts.json` — **Modified** (if applicable): The "auditor" entry may be replaced or redirected to the envelope assembler; if the monolithic prompt string remains as fallback, it must be clearly documented as deprecated

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft following ISSUE-1183 Planner-first pattern. Three-layer envelope (execution_contract -> reference_index -> final_checklist) reused as-is. Deterministic pre-flight validation preserved in Python. New `envelope_assembler.py` module created as role-agnostic helper. Auditor-specific contract and references injected via parameters.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### JSON Output Schema (Auditor Verdict)
The Auditor must output a JSON object with exactly the following structure. No additional fields may be added. The `status` field must be exactly `"APPROVED"` or `"REJECTED"` (case-sensitive).

```json
{"status": "APPROVED", "comments": "Clear and concise explanation of why the PRD meets the required standards."}
```

```json
{"status": "REJECTED", "comments": "Specific, actionable explanation of what is wrong and which architectural or content requirements are violated."}
```

### Startup Envelope Structure (JSON Schema)
The envelope assembler must produce a JSON object with exactly these top-level keys:

```json
{
  "execution_contract": {
    "role": "auditor",
    "mode": "standard|re-audit",
    "workdir": "/absolute/path/to/workdir",
    "prd_file": "/absolute/path/to/prd.md",
    "verdict_output_path": "/absolute/path/to/auditor_verdict.json",
    "json_output_schema": "{\"status\": \"APPROVED\"|\"REJECTED\", \"comments\": \"...\"}",
    "mandatory_read_rule": "Read all priority=1 references using native file tools before producing verdict.",
    "anti_yolo_rule": "Evaluate only. Never modify the PRD. Never auto-correct. Output only the verdict and comments."
  },
  "reference_index": [
    {
      "id": "prd",
      "kind": "prd",
      "path": "/absolute/path/to/prd.md",
      "required": true,
      "priority": 1,
      "purpose": "The document to audit. Must be read in full before producing verdict."
    },
    {
      "id": "playbook",
      "kind": "playbook",
      "path": "/absolute/path/to/auditor_playbook.md",
      "required": true,
      "priority": 1,
      "purpose": "Methodology and evaluation criteria for the audit."
    },
    {
      "id": "output_schema",
      "kind": "schema",
      "path": "/absolute/path/to/output_schema_reference.md",
      "required": true,
      "priority": 1,
      "purpose": "The exact JSON schema for the audit verdict output."
    }
  ],
  "final_checklist": [
    "PRD to audit: /absolute/path/to/prd.md",
    "Output verdict to: /absolute/path/to/auditor_verdict.json",
    "Output format: {\"status\": \"APPROVED\"|\"REJECTED\", \"comments\": \"...\"}",
    "Mandatory: Read all priority=1 references before producing verdict",
    "Anti-YOLO: Evaluate only. Never modify the PRD."
  ]
}
```

### Deterministic Pre-Flight Rejection Messages (Unchanged from existing)
These messages must be preserved exactly:

- **Missing sections error**: `"REJECTED: PRD structure does not match the mandatory template. Missing sections: {', '.join(missing_sections)}. DO NOT overwrite the template generated by init_prd.py with raw write tools."`

- **Missing Section 7 error**: `"REJECTED: The PRD mentions specific text/messages but fails to list them in 'Section 7. Hardcoded Content'. Ensure Coder has no room for hallucination."`

### None of the following apply (已确认不使用):
- 无 config 文件变更
- 无 shell 脚本变更
- 无新的 CLI 参数
