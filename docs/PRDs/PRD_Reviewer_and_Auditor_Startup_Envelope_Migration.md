---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Reviewer and Auditor Startup Envelope Migration

## 1. Context & Problem (业务背景与核心痛点)

### 1.1 Background

ISSUE-1183 established the three-layer startup envelope pattern (`execution_contract` → `reference_index` → `final_checklist`) for the Planner, replacing its complex monolithic prompt. The Planner refactor was validated and deployed. The PRD explicitly required the resulting architecture to be role-agnostic for later role migrations.

An initial attempt to migrate the Auditor alone (`PRD_Auditor_Startup_Envelope_Refactor.md`) was correctly rejected by the Auditor because it diagnosed a non-existent problem: the Auditor's prompt is already a short launcher + on-demand reading, not a monolithic inlined prompt. Migrating it alone would have been speculative abstraction.

### 1.2 Genuine Pain Point: Reviewer

The Reviewer (`spawn_reviewer.py`) has a verified monolithic prompt problem at the same scale as the original Planner issue. Evidence from the current runtime:

`spawn_reviewer.py` reads the full `reviewer_playbook.md` and passes it as `playbook_content` to `build_prompt("reviewer", ...)`. The `prompts.json["reviewer"]` template inlines this content via `{playbook_content}`, putting the entire methodology text inside the LLM's first-turn prompt. Additionally, the diff path, PR contract path, and output file path appear after the methodology text rather than being front-loaded as an execution contract.

This is the same structural fragility that ISSUE-1183 solved for the Planner:
- the most important execution constraints (which files to review, where to write the output, the output JSON schema) appear after the long methodology body,
- the LLM forms a high-level task interpretation from the methodology text before seeing the concrete execution contract,
- no startup packet is persisted for post-mortem debugging.

### 1.3 Auditor Alignment

The Auditor's prompt is structurally sound (short launcher + on-demand reading), but uses a different code path than the Planner envelope. From a homogeneity standpoint, migrating the Auditor to the same envelope assembler alongside the Reviewer:
- costs near-zero (Auditor is simpler than Reviewer in every dimension),
- eliminates the `build_prompt("auditor", ...)` code path,
- provides a second real consumer for the generalized envelope assembler, validating that the generalization is not speculative abstraction.

### 1.4 Planner Alignment

The current `planner_envelope.py` module is Planner-specific. With Reviewer and Auditor now sharing the same architecture, this module must be generalized into `envelope_assembler.py`. Planner's `spawn_planner.py` will be updated to use the generalized API. However, because Planner is already in production and existing tests may still import `planner_envelope.py`, backward compatibility must be preserved through a true adapter that keeps the old Planner signatures and legacy artifact filenames intact.

### 1.5 Explicitly NOT in Scope

- Coder startup path (stateful role with revision feedback loops; deferred to a separate follow-up PRD)
- Verifier startup path (deferred)
- Arbitrator startup path (deferred)
- Any changes to `agent_driver.py` or `invoke_agent()` transport mechanism
- Any changes to playbook content or methodology
- Any changes to deterministic pre-flight validation in `spawn_auditor.py`
- Any Coder, Verifier, or Orchestrator business logic changes

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Generalize planner_envelope.py into envelope_assembler.py**
   - Create `scripts/envelope_assembler.py` as a role-agnostic module.
   - Provide: `build_startup_envelope(role, workdir, out_dir, references, contract_params, mode)` → `dict`
   - Provide: `render_envelope_to_prompt(envelope)` → `str`
   - Provide: `save_envelope_artifacts(role, out_dir, envelope, rendered_prompt, extra_artifacts=None)` → writes role-scoped debug artifacts.
   - The returned envelope dict must include `role` as a top-level key so artifact routing and downstream inspection are deterministic.
   - The existing `planner_envelope.py` must become a true backward-compatible adapter that preserves the old Planner function signatures and legacy artifact filenames.
   - The startup protocol itself must be fully frozen in this PRD: fixed section headings, fixed section order, and a minimum `startup_packet.json` schema must all be explicitly defined in Section 7.

2. **Migrate Reviewer to use envelope_assembler**
   - `spawn_reviewer.py` must stop inlining `playbook_content` into the first-turn prompt.
   - The Reviewer startup payload must use the three-layer envelope: `execution_contract`, `reference_index`, `final_checklist`.
   - The `reference_index` must include the playbook path, the PRD path, the PR contract path, and the diff path.
   - The `execution_contract` must front-load the locked workdir, diff file path, PR contract path, PRD path, output file path, and the exact JSON output schema.
   - The `final_checklist` must repeat the highest-risk constraints.

3. **Migrate Auditor to use envelope_assembler**
   - `spawn_auditor.py` must replace `build_prompt("auditor", ...)` with `envelope_assembler.build_startup_envelope(role="auditor", ...)`.
   - All existing deterministic pre-flight checks in `spawn_auditor.py` (required sections check, Section 7 check) must remain as Python code and must NOT be moved into the LLM envelope.
   - The envelope must provide the same valid information currently in the short launcher prompt, structured in the three-layer format.
   - The exit-code policy (`sys.exit(0)` for both APPROVED and REJECTED) must be preserved.

4. **Update Planner to use the generalized API**
   - `spawn_planner.py` must update its imports from `planner_envelope` to `envelope_assembler`.
   - Function calls must be updated to the generalized API signatures.
   - Planner business logic (PR contract generation, mode selection, scaffold commands) must be unchanged.
   - All three Planner entry modes (standard, slice, UAT-replan) must continue to work identically.
   - Any stale internal caller or e2e reference that still imports `planner_envelope.py` must continue to work through a real adapter that preserves the old call signatures.

5. **Deprecate prompts.json entries for migrated roles**
   - The `"auditor"`, `"reviewer"`, and `"planner"` keys in `config/prompts.json` must be replaced with `"__DEPRECATED__"` marker strings.
   - The old prompt text must NOT be kept in the file; it becomes dead code.
   - `build_prompt()` in `agent_driver.py` must remain unchanged (Coder and Verifier still use it).
   - All other keys in `prompts.json` must be preserved unchanged.

6. **Observability artifacts for all three migrated roles**
   - Each invocation of Reviewer, Auditor, or Planner through the envelope assembler must persist:
     - `{role}_debug/startup_packet.json` — the structured envelope before rendering,
     - `{role}_debug/rendered_prompt.txt` — the actual prompt string sent to the LLM.
   - The artifact directory name must use the explicit `role` parameter and explicit `envelope["role"]` field.
   - For Planner only, the backward-compatible adapter must continue to write the legacy filenames `planner_debug/startup_prompt.txt` and `planner_debug/scaffold_contract.txt` in addition to the generalized artifacts, so existing tests and forensic flows do not break.
   - `spawn_planner.py`, `spawn_reviewer.py`, and `spawn_auditor.py` must each call `save_envelope_artifacts(...)` in both production mode and test mode. Artifact persistence must not depend on the engine, mock path, or runtime branch.

7. **No changes to agent_driver.py or invoke_agent()**
   - The temp-file transport mechanism and secure-message wrapping in `invoke_agent()` must remain unchanged.
   - The JIT guardrail (mandatory file I/O policy) must continue to be appended by `invoke_agent()`.

8. **No changes to any playbook file**
   - `playbooks/reviewer_playbook.md`, `playbooks/auditor_playbook.md`, and `playbooks/planner_playbook.md` must not be modified.
   - The envelope's `execution_contract` provides the authoritative mechanical constraints; the playbook remains methodological reference only.

9. **Auditor and Reviewer notification behavior unchanged**
   - Ignition handshake, channel notification, and event-type dispatch must remain identical to current behavior.
   - The exact runtime and notification strings covered by this requirement must be frozen in Section 7.

### 2.2 Non-Functional Requirements

1. The Reviewer's first-turn prompt must be materially shorter than the current monolithic prompt.
2. The non-Reviewer entry points (Auditor, Planner) must have first-turn prompts no longer than their current versions.
3. All existing E2E tests, mocked tests, and preflight checks must pass unchanged.
4. The `envelope_assembler.py` module must be importable and testable in isolation without requiring a full SDLC runtime.

### 2.3 Explicit Non-Goals

- No changes to Coder, Verifier, Arbitrator, or Orchestrator startup paths.
- No changes to `agent_driver.py`, `invoke_agent()`, or the temp-file transport.
- No playbook content changes.
- No changes to the `build_prompt()` function or its callers for non-migrated roles.
- No introduction of a task-brief or summary layer.
- No changes to deterministic pre-flight logic.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Architecture: Before and After

**Before (current state):**
```
spawn_planner.py  ──→  planner_envelope.py (Planner-specific)  ──→  invoke_agent()
spawn_auditor.py  ──→  build_prompt("auditor", ...)  ──→  prompts.json["auditor"]  ──→  invoke_agent()
spawn_reviewer.py ──→  build_prompt("reviewer", {playbook_content=全文})  ──→  prompts.json["reviewer"]  ──→  invoke_agent()
spawn_coder.py    ──→  build_prompt("coder", {playbook_content=全文, prd_content=全文, pr_content=全文})  ──→  prompts.json["coder"]  ──→  invoke_agent()
```

**After (this PRD):**
```
spawn_planner.py  ──→  envelope_assembler.py (role-agnostic)  ──→  invoke_agent()
spawn_auditor.py  ──→  envelope_assembler.py (role-agnostic)  ──→  invoke_agent()
spawn_reviewer.py ──→  envelope_assembler.py (role-agnostic)  ──→  invoke_agent()
spawn_coder.py    ──→  build_prompt("coder", ...)  ──→  prompts.json["coder"]  ──→  invoke_agent()   [unchanged, deferred]
```

### 3.2 envelope_assembler.py API Design

The module provides three public functions:

**`build_startup_envelope(role, workdir, out_dir, references, contract_params, mode="standard")` → `dict`**

Parameters:
- `role`: `"planner"` | `"auditor"` | `"reviewer"`
- `workdir`: locked working directory
- `out_dir`: output artifacts directory
- `references`: dict of role-specific reference paths
- `contract_params`: dict of role-specific contract fields
- `mode`: `"standard"` | `"re-audit"` | `"slice"` | `"uat"` — role-dependent

Returns a dict with keys: `role`, `execution_contract`, `reference_index`, `final_checklist`.

**`render_envelope_to_prompt(envelope)` → `str`**

Renders the envelope dict to a concise text prompt string with a fully frozen structure:
1. the literal heading `# EXECUTION CONTRACT`,
2. the execution contract bullet list,
3. a blank line,
4. the literal heading `# REFERENCE INDEX`,
5. the reference index block,
6. a blank line,
7. the literal heading `# FINAL CHECKLIST`,
8. the final checklist bullet list.

The rendered output must NOT include any reference body content.

**`save_envelope_artifacts(role, out_dir, envelope, rendered_prompt, extra_artifacts=None)` → `None`**

Persists two required files under `{out_dir}/{role}_debug/`:
- `startup_packet.json`: the raw envelope dict as JSON
- `rendered_prompt.txt`: the rendered prompt string

If `extra_artifacts` is provided, each `{name: content}` pair must be written under the same `{role}_debug/` directory. This is how the Planner adapter preserves its legacy `scaffold_contract.txt` forensic artifact.

### 3.3 Role-Specific Contract Parameters

**Reviewer contract_params:**
```python
{
    "output_file": "{workdir}/{run_dir}/review_report.json",
    "output_schema": {
        "overall_assessment": "(EXCELLENT|GOOD_WITH_MINOR_SUGGESTIONS|NEEDS_ATTENTION|NEEDS_IMMEDIATE_REWORK)",
        "executive_summary": "string",
        "findings": [
            {
                "file_path": "string",
                "line_number": "integer",
                "category": "(Correctness|PlanAlignmentViolation|ArchAlignmentViolation|Efficiency|Readability|Maintainability|DesignPattern|Security|Standard|PotentialBug|Documentation)",
                "severity": "(CRITICAL|MAJOR|MINOR|SUGGESTION|INFO)",
                "description": "string",
                "recommendation": "string"
            }
        ]
    }
}
```

**Reviewer references:**
```python
{
    "prd_file": prd_file_abs,
    "pr_contract_file": pr_file_abs,
    "diff_file": diff_file_abs,
    "playbook_path": playbook_abs,
}
```

**Auditor contract_params:**
```python
{
    "output_file": "{run_dir}/auditor_verdict.json",
    "output_schema": {
        "reasoning": "string",
        "status": "APPROVED|REJECTED",
        "comments": "string"
    }
}
```

**Auditor references:**
```python
{
    "prd_file": prd_file_abs,
    "playbook_path": playbook_abs,
}
```

### 3.4 Planner backward compatibility

`planner_envelope.py` must be preserved as a true backward-compatible adapter, not an alias-only shim:

```python
# planner_envelope.py — backward-compatible adapter
from envelope_assembler import build_startup_envelope, render_envelope_to_prompt, save_envelope_artifacts

def build_planner_envelope(workdir, out_dir, prd_path, playbook_path, template_path, contract_script, mode="standard", uat_report_path=None, failed_pr_id=None):
    # translate the old Planner-specific signature to the generalized API
    ...

def render_planner_prompt(envelope):
    return render_envelope_to_prompt(envelope)

def save_debug_artifacts(out_dir, envelope_dict, rendered_prompt, scaffold_command):
    # preserve old artifact filenames and behavior exactly
    save_envelope_artifacts(
        role="planner",
        out_dir=out_dir,
        envelope=envelope_dict,
        rendered_prompt=rendered_prompt,
        extra_artifacts={
            "startup_prompt.txt": rendered_prompt,
            "scaffold_contract.txt": scaffold_command,
        },
    )
```

This is a real adapter because it preserves:
- the old function names,
- the old argument shape,
- the old legacy artifact filenames.

The migration boundary must be explicit:
- `envelope_assembler.py` is the only new canonical startup-assembly implementation for Planner, Reviewer, and Auditor.
- `spawn_planner.py` must call `envelope_assembler.py` directly as the production path.
- `planner_envelope.py` exists only as a compatibility adapter for stale internal imports and test fixtures. It must not grow independent logic or become a second canonical protocol path.

### 3.5 Reviewer: Diff-Centric Startup Envelope

The Reviewer's `execution_contract` must include:
- the locked workdir,
- the exact diff file path,
- the exact PR contract file path,
- the exact PRD file path,
- the exact output file path,
- the exact JSON schema for the review report,
- the mandatory read rule,
- a no-speculative-changes rule: evaluate only, never modify code.

The Reviewer's `reference_index` must include:
- PRD (`priority=1`)
- PR Contract (`priority=1`)
- Diff file (`priority=1`)
- Reviewer Playbook (`priority=1`)

### 3.6 Auditor: Minimal Migration

The Auditor's migration is deliberately minimal. The `execution_contract` captures what the current short prompt already says, plus:
- the explicit output path,
- the explicit JSON schema,
- the mandatory read rule,
- the anti-YOLO rule.

The deterministic pre-flight checks in `spawn_auditor.py` are NOT moved into the envelope. They run as Python code before any envelope assembly, exactly as today.

### 3.7 prompts.json Deprecation Format

Each deprecated key must be replaced with exactly:

```json
"auditor": "__DEPRECATED__ use envelope_assembler.py — see spawn_auditor.py",
"reviewer": "__DEPRECATED__ use envelope_assembler.py — see spawn_reviewer.py",
"planner": "__DEPRECATED__ use envelope_assembler.py — see spawn_planner.py"
```

The deprecated markers exist only to make dead code obvious on inspection. They are not part of any active runtime path after the migration.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Reviewer prompt no longer inlines playbook**
  - **Given** a valid PR contract and diff exist for review
  - **When** `spawn_reviewer.py` runs in test mode (`SDLC_TEST_MODE=true`)
  - **Then** the saved `reviewer_debug/rendered_prompt.txt` must NOT contain the full text of `reviewer_playbook.md`, and the first section of the prompt must be the execution contract

- **Scenario 2: Auditor prompt uses three-layer envelope structure**
  - **Given** a valid PRD exists
  - **When** `spawn_auditor.py` runs in test mode
  - **Then** the saved `auditor_debug/rendered_prompt.txt` must begin with execution contract content and contain a reference index section and a final checklist section

- **Scenario 3: Planner continues to work identically after API migration**
  - **Given** a valid PRD exists
  - **When** `spawn_planner.py` runs in test mode with the same input as before the refactor
  - **Then** the generated rendered prompt must produce the same output directory, the same scaffold command, and the same reference paths as the pre-refactor version
  - **And** the only canonical production startup-assembly path must be `spawn_planner.py` → `envelope_assembler.py`; `planner_envelope.py` may only act as a compatibility adapter for stale imports and tests

- **Scenario 4: Auditor pre-flight checks unchanged**
  - **Given** a PRD missing Section 7
  - **When** `spawn_auditor.py` runs
  - **Then** the script must reject the PRD before any LLM invocation, printing exactly:
    `"REJECTED: The PRD mentions specific text/messages but fails to list them in 'Section 7. Hardcoded Content'. Ensure Coder has no room for hallucination."`

- **Scenario 5: envelope_assembler produces role-scoped startup artifacts deterministically**
  - **Given** `build_startup_envelope(role="reviewer", ...)` is called
  - **When** the returned envelope dict and rendered prompt are passed to `save_envelope_artifacts(role="reviewer", out_dir, envelope, prompt)`
  - **Then** `{out_dir}/reviewer_debug/startup_packet.json` and `{out_dir}/reviewer_debug/rendered_prompt.txt` must exist with valid content

- **Scenario 6: Planner adapter preserves old artifact names and call shape**
  - **Given** existing Planner code or e2e tests still call `build_planner_envelope(...)`, `render_planner_prompt(...)`, and `save_debug_artifacts(out_dir, envelope, rendered_prompt, scaffold_command)` with the old signatures
  - **When** those calls execute after the migration
  - **Then** they must succeed without argument-shape changes, and `planner_debug/startup_packet.json`, `planner_debug/startup_prompt.txt`, and `planner_debug/scaffold_contract.txt` must still be created as before

- **Scenario 7: Existing e2e tests pass**
  - **Given** the full test suite in `tests/` and `scripts/e2e/`
  - **When** `./preflight.sh` runs
  - **Then** all tests must pass with exit code 0

- **Scenario 8: prompts.json deprecated keys produce no runtime errors**
  - **Given** `prompts.json` has `"__DEPRECATED__"` markers for auditor/reviewer/planner keys
  - **When** `agent_driver.py` is imported and `build_prompt("coder", ...)` is called
  - **Then** it must work correctly without errors; the deprecated keys must not be loaded by any active code path

- **Scenario 9: Reviewer reference_index contains all required files**
  - **Given** `build_startup_envelope(role="reviewer", ...)` is called with valid references
  - **When** the startup packet is inspected
  - **Then** the `reference_index` must contain entries for PRD file, PR contract file, diff file, and reviewer playbook, all with `priority=1` and `required=true`

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk

The primary risk is not qualitative LLM drift; it is structural regression in startup assembly, artifact persistence, or backward compatibility. Reviewer is the most complex of the three migrated roles because it currently inlines its playbook and has the richest JSON output schema.

### Mitigation Strategy

1. **Artifact-based structural validation (primary)**: Verify that:
   - `rendered_prompt.txt` does NOT contain inlined playbook content,
   - `execution_contract` appears before `reference_index`,
   - `startup_packet.json` is structurally valid for each role,
   - the envelope assembler is not role-specific (accepts explicit `role` parameter and returns explicit `envelope["role"]`).

2. **Mocked LLM testing**: Run all three roles' spawn scripts with `SDLC_TEST_MODE=true` to verify the full pipeline (pre-flight → envelope assembly → prompt render → verdict capture) does not break.

3. **Snapshot comparison for Planner**: A diff test comparing Planner's rendered prompt before and after the refactor to prove only module/API wiring changed, not business contract content.

4. **No live LLM equivalence test**: Qualitative LLM behavior is non-deterministic. Testing focuses on deterministic structural properties only.

### Test Types

| Test Type | Scope | Required |
|---|---|---|
| Unit tests | `envelope_assembler.py` — envelope structure, rendering, role parameterization | Yes |
| Integration tests | `spawn_reviewer.py`, `spawn_auditor.py`, `spawn_planner.py` — envelope integration | Yes |
| E2E mocked tests | Full spawn scripts with `SDLC_TEST_MODE=true` | Yes |
| Snapshot tests | Planner before/after prompt comparison | Yes |
| Artifact tests | `{role}_debug/startup_packet.json` and `rendered_prompt.txt` creation | Yes |
| Live LLM tests | Qualitative verdict comparison | No |

## 6. Framework Modifications (框架防篡改声明)

- `scripts/envelope_assembler.py` — **New File**: Role-agnostic startup envelope builder, prompt renderer, and artifact saver. Generalizes the existing `planner_envelope.py` logic into a parameter-driven module.

- `scripts/planner_envelope.py` — **Modified**: Become a true backward-compatible adapter that preserves the old function signatures and legacy artifact filenames while delegating to `envelope_assembler.py`. No Planner business logic changes.

- `scripts/spawn_planner.py` — **Modified**: Update imports from `planner_envelope` to `envelope_assembler`. Update function calls to the generalized API (`build_startup_envelope`, `render_envelope_to_prompt`, `save_envelope_artifacts`). Mode selection and scaffold logic unchanged.

- `scripts/spawn_reviewer.py` — **Modified**: Replace `build_prompt("reviewer", playbook_content=..., pr_content=..., ...)` with `envelope_assembler.build_startup_envelope(role="reviewer", ...)`. Remove the `playbook_content` file read (keep the playbook path for the reference index). Guardrail check logic unchanged.

- `scripts/spawn_auditor.py` — **Modified**: Replace `build_prompt("auditor", ...)` with `envelope_assembler.build_startup_envelope(role="auditor", ...)`. All deterministic pre-flight validation logic unchanged. Exit-code policy unchanged.

- `config/prompts.json` — **Modified**: Replace `"auditor"`, `"reviewer"`, and `"planner"` values with `"__DEPRECATED__"` marker strings. All other keys preserved unchanged.

- **Files NOT modified by this PRD**:
  - `scripts/agent_driver.py`
  - `scripts/spawn_coder.py`
  - `scripts/spawn_verifier.py`
  - `scripts/orchestrator.py`
  - `playbooks/reviewer_playbook.md`
  - `playbooks/auditor_playbook.md`
  - `playbooks/planner_playbook.md`
  - `playbooks/coder_playbook.md`
  - `playbooks/verifier_playbook.md`
  - `playbooks/forensic_agent_playbook.md`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0 (Rejected)**: Initial draft as `PRD_Auditor_Startup_Envelope_Refactor.md`. Proposed Auditor-only refactor with `envelope_assembler.py`, incorrectly diagnosed a non-existent monolithic prompt problem in Auditor. Rejected by Auditor on grounds of speculative abstraction and white-box AC.
- **v2.0 (Rejected)**: Shifted primary target from Auditor to Reviewer, but still had four execution-safety defects: incomplete String Determinism, fake Planner backward compatibility, under-specified artifact saver API, and a subjective AC about qualitative equivalence.
- **v3.0 (This PRD)**: Keeps Reviewer as the primary target and Auditor as secondary alignment, but fixes the four execution-safety defects: all exact runtime strings frozen in Section 7, Planner wrapper upgraded to a real adapter, `role` made explicit in both the saver API and envelope schema, and subjective AC replaced with deterministic structural checks.

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**

### 7.1 prompts.json Deprecated Key Values

Replace the values of these keys in `config/prompts.json`:

- **For `"auditor"` key**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_auditor.py
```

- **For `"reviewer"` key**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_reviewer.py
```

- **For `"planner"` key**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_planner.py
```

### 7.2 Existing Auditor Error Messages (Preserved Unchanged)

- **Missing sections error**:
```text
REJECTED: PRD structure does not match the mandatory template. Missing sections: {', '.join(missing_sections)}. DO NOT overwrite the template generated by init_prd.py with raw write tools.
```

- **Missing Section 7 error**:
```text
REJECTED: The PRD mentions specific text/messages but fails to list them in 'Section 7. Hardcoded Content'. Ensure Coder has no room for hallucination.
```

### 7.3 Notification and Runtime Strings Preserved Unchanged

- **Envelope rendered prompt heading 1**:
```text
# EXECUTION CONTRACT
```

- **Envelope rendered prompt heading 2**:
```text
# REFERENCE INDEX
```

- **Envelope rendered prompt heading 3**:
```text
# FINAL CHECKLIST
```

- **startup_packet.json minimum top-level schema**:
```json
{
  "role": "planner|reviewer|auditor",
  "execution_contract": ["string", "..."],
  "reference_index": [
    {
      "id": "string",
      "kind": "string",
      "path": "/absolute/path",
      "required": true,
      "priority": 1,
      "purpose": "string"
    }
  ],
  "final_checklist": ["string", "..."]
}
```

- **Ignition handshake**:
```text
🤝 [SDLC Engine] Initial Handshake successful. Channel linked.
```

- **Auditor start notification (with command)**:
```text
🚀 [Auditor] Starting PRD audit for: {prd_file}
💻 Command: `{cmd}`
```

- **Auditor start notification (without command)**:
```text
🚀 [Auditor] Starting PRD audit for: {prd_file}
```

- **Auditor approved notification**:
```text
✅ [Auditor] PRD 审查通过 (APPROVED)。
```

- **Auditor rejected notification**:
```text
❌ [Auditor] PRD 审查未通过 (REJECTED)，请根据反馈进行修改并重试。
```

- **Reviewer spawned notification**:
```text
🔍 [Reviewer] Auditing changes for {pr_match}...
```

- **Reviewer start notification (legacy)**:
```text
🔍 [Reviewer] Auditing changes for {pr_match}...
```

- **Reviewer result notification (legacy)**:
```text
📝 6. [{pr_match}] Review 结果：{result}
```

- **Reviewer rejected notification (legacy)**:
```text
❌ Reviewer rejected changes. Reason: {summary}. Retrying...
```

### 7.4 Reviewer Output JSON Schema (Unchanged from current)

```json
{
  "overall_assessment": "(EXCELLENT|GOOD_WITH_MINOR_SUGGESTIONS|NEEDS_ATTENTION|NEEDS_IMMEDIATE_REWORK)",
  "executive_summary": "string",
  "findings": [
    {
      "file_path": "string",
      "line_number": "integer",
      "category": "(Correctness|PlanAlignmentViolation|ArchAlignmentViolation|Efficiency|Readability|Maintainability|DesignPattern|Security|Standard|PotentialBug|Documentation)",
      "severity": "(CRITICAL|MAJOR|MINOR|SUGGESTION|INFO)",
      "description": "string",
      "recommendation": "string"
    }
  ]
}
```

### 7.5 None of the following apply (已确认不使用):
- 无新的 CLI 参数
- 无新的 config 文件
- 无新的 shell 脚本
- 无 playbook 内容变更
