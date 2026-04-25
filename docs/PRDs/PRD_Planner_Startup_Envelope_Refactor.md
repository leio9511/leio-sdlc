---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Planner Startup Envelope Refactor

## 1. Context & Problem (业务背景与核心痛点)
`ISSUE-1183` exposed that the current Planner startup path is architecturally fragile under long execution briefs.

The current `spawn_planner.py` flow builds one oversized natural-language startup prompt by directly inlining:
- the Planner playbook,
- the full PRD body,
- the PR contract template,
- and the concrete mechanical execution contract.

This layout is brittle because the most important execution constraint can appear hundreds of lines after the model has already formed a high-level task interpretation. In the reproduced `PRD_Config_Driven_Multi_CLI_Engine_Integration` failure, the orchestrator and `spawn_planner.py` correctly computed the active `run_dir/job_dir`, and the saved prompt metadata proved that the correct `create_pr_contract.py --job-dir ...` contract was present. However, the concrete command appeared extremely late in a very long prompt, while generated PR artifacts still landed in the legacy `docs/PRs/...` path. The failure is therefore not best explained by path computation bugs. It is best explained by startup-prompt architecture failure: the concrete execution contract was buried inside a monolithic prompt and was not given sufficient structural priority.

This PRD intentionally scopes the fix to the Planner only.
That is a deliberate design choice, not a compromise. If we attempt to redesign the startup prompts for Planner, Reviewer, Coder, Verifier, Auditor, and Arbitrator in one PRD, the execution brief itself will likely become so long that it repeats the same long-context failure mode this issue is trying to solve.

Accordingly, this PRD defines a **Planner-first, architecturally complete** refactor:
- land the full target startup-envelope architecture on Planner,
- use Planner as the reference implementation / archetype,
- leave other agents unchanged for now,
- migrate other agents later under separate follow-up issues / PRDs using the same validated pattern.

The design direction is also aligned with current industry best practice for agent context initialization:
- front-load short, high-priority instructions,
- separate execution contract from long references,
- prefer progressive disclosure / on-demand reading over giant inlined prompts,
- make context assembly observable and replayable.

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. **Planner-only scope for this PRD**
   - This PRD must modify only the Planner startup path.
   - Reviewer, Coder, Verifier, Auditor, and Arbitrator prompt/playbook refactors are explicitly out of scope.
   - The implementation must nevertheless produce a reusable architectural baseline for later role migrations.

2. **Replace the monolithic Planner startup prompt with a startup envelope**
   - The Planner startup payload must be restructured into exactly three ordered layers:
     1. `execution_contract`
     2. `reference_index`
     3. `final_checklist`
   - The first visible startup content for the Planner must be the execution contract, not the full PRD body, not the playbook, and not the template body.

3. **No `task brief` in Phase 1**
   - The Planner startup envelope for this PRD must not include a `task_brief` field or any equivalent manually-authored summary layer.
   - This is a deliberate anti-distortion guardrail: the refactor must improve context structure without introducing a new failure mode where a bad summary silently changes the task.

4. **Reference-index-driven progressive disclosure**
   - The Planner startup payload must no longer inline the full contents of:
     - `prd_content`
     - `playbook_content`
     - `template_content`
   - Instead, the startup payload must provide a structured `reference_index` containing absolute paths and minimal metadata for required references.
   - The Planner must be instructed to use native file reads to load those references on demand.

5. **Role-specific mandatory references**
   - For the Planner path, the `reference_index` must include exactly these required, priority-1 references:
     - the authoritative PRD,
     - the Planner playbook,
     - the PR contract template.
   - Before producing any artifact, the Planner must be instructed to read all required references with `priority=1`.

6. **Mechanical execution contract must be front-loaded and explicit**
   - The Planner execution contract must explicitly state all of the following before the reference index:
     - the locked `workdir`,
     - the exact output directory (`run_dir/job_dir/out_dir`),
     - the rule that the active output directory is the only valid location for PR contract artifacts in the current run,
     - the exact required scaffold command using `create_pr_contract.py`,
     - the completion condition that PR contracts must physically exist under the exact active output directory.

7. **Preserve current Planner business behavior while changing startup architecture**
   - The Planner must still generate dependency-ordered Micro-PR contracts.
   - The `--slice-failed-pr` path must still preserve the existing `--insert-after {failed_pr_id}` contract for re-slicing.
   - The `--replan-uat-failures` path must continue to support focused UAT recovery planning.
   - The refactor must not weaken existing TDD guardrails or target-working-set requirements.

8. **All Planner entry paths must use the same startup-envelope architecture**
   - The Planner startup-envelope architecture in this PRD must cover all three runtime entry modes:
     1. standard PRD planning,
     2. failed-PR slicing,
     3. UAT-miss replanning.
   - These modes may differ in task wording and required references, but they must not use separate legacy giant-prompt assembly paths.

9. **Planner observability artifacts are mandatory**
   - Each real Planner invocation must save durable runtime artifacts proving what startup context was assembled.
   - At minimum, the runtime must persist:
     - the structured startup packet / envelope data,
     - the rendered startup prompt that was actually sent to the Planner,
     - the resolved scaffold command / contract evidence showing the exact `create_pr_contract.py --job-dir ...` contract for that run.
   - These artifacts must land inside the active run directory so the next repro can be debugged from hard evidence rather than inference.

10. **Planner remains the reference implementation only**
   - This PRD must explicitly frame the resulting architecture as the baseline pattern for later agent migrations.
   - It must not bundle those later migrations into the same implementation scope.

11. **Planner playbook boundary must be cleaned up as part of this refactor**
   - This PRD does not require a wholesale rewrite of `planner_playbook.md`, but it does require a role-boundary cleanup.
   - The Planner playbook must retain long-lived planning methodology only.
   - Run-specific execution constraints must not be relied on from the playbook.
   - In particular, the active output directory, exact scaffold command, required-read ordering, and run completion condition must live in `execution_contract`, not in the long-lived playbook body.

12. **Forward-compatibility with later role migrations is mandatory**
   - The startup-envelope shape introduced in this PRD must be designed as a role-agnostic baseline rather than a Planner-only dead end.
   - The three top-level layers `execution_contract`, `reference_index`, and `final_checklist` must remain generic enough to support later migration of Auditor, Coder, Reviewer, and Verifier without renaming the architecture or redesigning the packet shape.
   - Role-specific behavior must be expressed by per-role contract text and per-role reference entries, not by changing the envelope topology.
   - The implementation must avoid Planner-specific assumptions that would make later stateful roles impossible to migrate, such as assuming a single task mode, assuming all references are PRD/template-only, or assuming the role has no persistent-session feedback loop.

13. **A forward-compatibility review must be part of this PRD's acceptance bar**
   - This PRD must explicitly check that the resulting envelope design can represent at least the following future role families without structural redesign:
     - Auditor style: one-shot read-only audit over PRD + playbook + output schema,
     - Reviewer style: diff- and contract-centric review with follow-up system-alert recovery,
     - Verifier style: PRD/UAT verification against codebase plus output artifact,
     - Coder style: stateful execution role with revision feedback loops.
   - The goal is not to implement those roles now, but to prove the Planner-first architecture will not need a second foundational rewrite later.

### Non-Functional Requirements
1. The new Planner startup prompt must remain materially shorter and structurally clearer than the current monolithic inline prompt for long PRDs.
2. The design must reduce long-context instruction burying without depending on a manually-authored task summary.
3. The solution must be deterministic and auditable: the startup packet, rendered prompt, and resolved paths must be inspectable after the run.
4. The solution must preserve current Planner safety boundaries around output placement and file-generation flow.
5. The resulting architecture must be reusable by later roles, but this PRD must not require those later roles to be implemented now.

### Explicit Non-Goals
- redesigning all agent startup prompts in one PRD,
- rewriting all playbooks in this PRD,
- changing Reviewer/Coder/Verifier/Auditor/Arbitrator behavior,
- introducing a task-summary authoring pipeline,
- broad SDLC orchestrator state-machine redesign,
- replacing the Planner with a different engine/runtime model.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Core design principle
The Planner startup path must move from **monolithic prompt concatenation** to **contract-first progressive disclosure**.

The startup payload should no longer try to preload every important document into one giant first-turn prompt. Instead, it should:
1. put the highest-priority mechanical contract first,
2. provide a role-specific reference index for mandatory reads,
3. finish with a short checklist repeating the critical contract,
4. rely on on-demand reading of long materials through native file tools.

### 3.2 Planner startup envelope structure
The Planner startup architecture for this PRD must be built around a structured startup envelope with exactly these top-level layers:

1. **`execution_contract`**
   - role identity: Planner,
   - locked workdir,
   - exact output directory,
   - active-output-location exclusivity rule,
   - exact scaffold command,
   - mandatory-read rule for required priority-1 references,
   - completion condition.

2. **`reference_index`**
   - structured list of absolute-path references,
   - each reference includes only minimal routing metadata,
   - no business summary layer,
   - no full document bodies inline.

3. **`final_checklist`**
   - short repeated checklist of the highest-risk execution constraints,
   - especially exact output path, exact scaffold command, active-output-location exclusivity rule, and done condition.

This three-layer envelope is the full target state for Planner in this PRD.

### 3.3 No task-brief layer in this PRD
Although a compact task summary might look attractive, this PRD explicitly rejects it for Planner Phase 1.

Reason:
- a manually-authored or weakly-generated task brief can distort the authoritative PRD,
- different roles need different summaries,
- adding summary generation now would widen scope and create another ambiguity channel,
- the immediate 1183 problem is structural priority, not lack of summarization.

Therefore, this PRD must solve the startup-context problem using only:
- execution contract,
- reference index,
- final checklist.

### 3.4 Reference index rules
The `reference_index` is not a free-form file list. It must be structured and role-aware.

Each Planner reference entry must contain:
- `id`
- `kind`
- `path`
- `required`
- `priority`
- `purpose`

Constraints:
- `purpose` must be short and mechanical, not a business-summary paragraph.
- `required` must be boolean.
- `priority` must be numeric and support mandatory front-loading of the most important references.
- For this PRD, Planner must use exactly these required `priority=1` references:
  - authoritative PRD,
  - Planner playbook,
  - PR contract template.

### 3.5 Planner prompt rendering strategy
The rendered Planner prompt sent through `invoke_agent()` must become a short launcher prompt derived from the startup envelope.

It must:
- present the execution contract first,
- present the reference index second,
- present the final checklist last,
- instruct the Planner to read all required `priority=1` references before producing artifacts,
- avoid embedding the raw full contents of the PRD, playbook, and template directly into the first-turn prompt.

For this PRD, the Planner startup envelope must be constructed directly in the Planner runtime path (for example in `spawn_planner.py` or a Planner-specific helper), not through the legacy `config/prompts.json` `planner` / `planner_slice` giant-string templates.

The existing `agent_driver.py` secure temp-file transport may remain unchanged. The critical change is the content architecture of the Planner startup payload, not the outer transport mechanism.

### 3.6 Planner entry-mode unification
This PRD treats Planner as one role with three task modes, not three unrelated prompt systems.

The following runtime entry modes must all use the same three-layer startup envelope architecture:
1. standard PRD planning,
2. failed-PR slicing,
3. UAT-miss replanning.

Allowed differences per mode:
- task sentence inside `execution_contract`,
- mode-specific required references inside `reference_index`,
- mode-specific scaffold-command details such as `--insert-after {failed_pr_id}`.

Disallowed difference:
- falling back to a separate legacy giant prompt that directly inlines long reference bodies.

#### UAT-miss replanning mode
For the `--replan-uat-failures` path, the execution contract must narrow the Planner task to targeted recovery planning rather than whole-PRD replanning.

The UAT mode contract must explicitly constrain the Planner to generate focused Micro-PR contracts only for requirements marked missing or partial in the UAT report, without replanning already-satisfied functionality.

For UAT mode, the `reference_index` must include the UAT report as a required `priority=1` reference in addition to the normal required Planner references.

### 3.7 Playbook treatment in this PRD
This PRD does **not** require a wholesale rewrite of `planner_playbook.md`.

Instead:
- the Planner playbook must be demoted from inline prompt body to mandatory reference,
- hard mechanical rules that cannot risk being buried must live in `execution_contract`,
- the playbook must retain long-lived planning methodology only,
- run-specific constraints such as `{out_dir}`, exact scaffold command, required-read ordering, and run completion condition must not be relied on from the playbook body.

This is intentionally the first step toward a later long-term separation of:
- **role contract** (short, hard, front-loaded), and
- **role handbook/playbook** (longer, methodological, read on demand).

But for this PRD, only the Planner startup path is being refactored.

### 3.8 Observability design
The runtime must persist Planner startup evidence inside the active run directory.

Recommended artifact set:
- `planner_debug/startup_packet.json`
- `planner_debug/startup_prompt.txt`
- `planner_debug/scaffold_contract.txt`

Equivalent filenames are acceptable only if they preserve the same information clearly.

The saved evidence must allow a later human or agent to answer all of the following without inference:
- What exact execution contract did Planner receive?
- What exact output directory was specified?
- What exact scaffold command was specified?
- Which references were marked required?
- Did the runtime still inline long bodies by mistake?

### 3.9 Forward-compatibility contract for later role migrations
Although this PRD only implements Planner, the startup-envelope architecture must be judged as a reusable baseline for future role migrations.

The compatibility contract is:
- the top-level packet shape stays fixed as `execution_contract + reference_index + final_checklist`,
- per-role variance happens inside contract wording and reference-index contents,
- task mode differences are expressed as contract/reference variants rather than new prompt architectures,
- observability artifacts remain the same class of evidence for every role: startup packet, rendered prompt, role-specific contract evidence.

To avoid future rewrites, this PRD must preserve support for these later migration patterns:

1. **Auditor-compatible shape**
   - one-shot role,
   - required references may include PRD, auditor playbook, and output schema,
   - contract may require strict output format and read-only behavior.

2. **Reviewer-compatible shape**
   - stateful or follow-up-capable role,
   - required references may include PRD, PR contract, diff, review schema/template,
   - contract may require recovery follow-ups after malformed output or system alerts.

3. **Verifier-compatible shape**
   - one-shot but evidence-heavy role,
   - required references may include one or more PRDs, verifier playbook, output path, and verification target artifacts,
   - contract may require explicit validation against codebase state rather than contract generation.

4. **Coder-compatible shape**
   - stateful role with revision loops,
   - required references may include PR contract, PRD, coder playbook, and revision feedback artifacts,
   - contract may require persistent session continuity plus repeated follow-up turns.

The architecture introduced here is acceptable only if these future roles can be represented by changing role-specific content and helper logic without changing the envelope topology itself.

### 3.10 Implementation boundary
This PRD is expected to primarily target the Planner startup path, likely centered on `scripts/spawn_planner.py` plus any minimal supporting prompt/rendering helpers and tests.

The implementation should remain narrow:
- refactor Planner startup context assembly,
- preserve Planner business objective and output semantics,
- do not bundle multi-role migration into the same change.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Planner startup contract is front-loaded**
  - **Given** a Planner invocation for a long PRD
  - **When** the rendered startup prompt is inspected
  - **Then** the first high-priority section is the Planner execution contract
  - **And** the exact output directory and exact scaffold command appear before the reference index
  - **And** the full PRD/playbook/template bodies are not inlined ahead of that contract

- **Scenario 2: Planner uses reference-index-driven startup instead of monolithic inline bodies**
  - **Given** a Planner invocation
  - **When** the startup packet and rendered startup prompt are inspected
  - **Then** the startup envelope contains a structured `reference_index`
  - **And** the required priority-1 references include PRD, Planner playbook, and PR contract template
  - **And** the startup prompt does not directly inline the full contents of those three references

- **Scenario 3: Planner contract defines the active output location as exclusive**
  - **Given** a Planner invocation with a resolved active output directory
  - **When** the execution contract is inspected
  - **Then** it explicitly defines that active output directory as the only valid destination for PR contract artifacts in the current run
  - **And** it does not rely on a project-specific historical bad-path warning to express that rule

- **Scenario 4: Planner must read required references before artifact creation**
  - **Given** a Planner startup envelope
  - **When** the execution contract is inspected
  - **Then** it explicitly instructs the Planner to read every required `priority=1` reference before producing any artifact

- **Scenario 5: Planner output lands only in the exact active run directory**
  - **Given** a Planner run for a PRD with a resolved active `run_dir/job_dir`
  - **When** the Planner successfully generates Micro-PR contracts
  - **Then** the physical PR contract files appear under that exact active output directory
  - **And** artifacts written outside that active output location are treated as invalid for the run

- **Scenario 6: Failed-PR slicing behavior is preserved**
  - **Given** a Planner run triggered through `--slice-failed-pr`
  - **When** the startup envelope is rendered
  - **Then** the exact `--insert-after {failed_pr_id}` contract remains present in the scaffold command path or equivalent Planner execution contract
  - **And** generated sliced PR contracts preserve the expected sequential ordering behavior

- **Scenario 7: UAT-miss replanning also uses the startup envelope architecture**
  - **Given** a Planner run triggered through `--replan-uat-failures`
  - **When** the startup packet and rendered startup prompt are inspected
  - **Then** they use the same three-layer startup-envelope architecture as the other Planner modes
  - **And** the UAT report appears in the reference index as a required `priority=1` reference
  - **And** the execution contract explicitly constrains the Planner to generate contracts only for missing or partial UAT findings rather than replanning already-satisfied functionality

- **Scenario 8: Planner observability artifacts exist for repro debugging**
  - **Given** a real Planner invocation
  - **When** the run directory is inspected after launch or failure
  - **Then** durable startup evidence exists for the structured startup packet, rendered startup prompt, and scaffold contract/path evidence
  - **And** that evidence is sufficient to reconstruct what the Planner was told without relying on guesswork

- **Scenario 9: Planner-first envelope is forward-compatible with later role migrations**
  - **Given** the startup-envelope design produced by this PRD
  - **When** it is reviewed against future Auditor, Reviewer, Verifier, and Coder migration needs
  - **Then** those future roles can all be represented using the same top-level envelope shape
  - **And** role differences can be expressed through contract text, reference-index contents, and role-specific helper logic rather than a second foundational redesign

- **Scenario 10: Other roles remain unchanged by this PRD**
  - **Given** this PRD implementation is applied
  - **When** Reviewer, Coder, Verifier, Auditor, and Arbitrator startup paths are inspected
  - **Then** they are not silently migrated to the new envelope architecture as part of this change

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
The core risk is not basic path computation. The core risk is that long-context startup prompts bury mechanical execution constraints, causing Planner to follow the general planning intent while ignoring the exact artifact-creation contract.

### Verification Strategy
1. **Deterministic contract-rendering tests**
   - Add tests that assert the Planner startup envelope contains the required top-level layers in the correct order.
   - Assert that the rendered Planner prompt no longer directly embeds full `prd_content`, `playbook_content`, or `template_content` bodies.
   - Assert that all Planner entry modes use the envelope architecture rather than legacy giant-string prompt assembly.
   - Assert that required priority-1 references are present in the reference index.

2. **Deterministic contract-content tests**
   - Assert the execution contract includes the exact active output directory.
   - Assert the execution contract defines that directory as the only valid artifact location for the run.
   - Assert the scaffold contract includes the exact `create_pr_contract.py --job-dir ...` path.
   - Assert the failed-PR slicing path preserves the exact `--insert-after {failed_pr_id}` contract.
   - Assert the UAT replanning path includes the UAT report as a required `priority=1` reference and narrows the task to missing/partial UAT findings only.
   - Assert no `task_brief` top-level field is emitted.

3. **Mocked Planner flow tests**
   - Extend or add mocked tests around `spawn_planner.py` so a long PRD still produces a short startup envelope.
   - Verify that Planner artifacts generated under test mode still land in the active output directory.
   - Verify that the failed-PR slicing path still preserves `--insert-after` behavior.

4. **Observability artifact tests**
   - Add tests proving the startup packet / rendered prompt / scaffold-contract evidence files are written into the active run directory.
   - These tests should fail if the runtime stops saving the debug evidence.

5. **Forward-compatibility design review**
   - Add a deterministic design-level test or explicit contract assertion proving the Planner-first envelope can represent future Auditor, Reviewer, Verifier, and Coder role families without changing the top-level packet shape.
   - This may be implemented as a schema-level test, a helper-level compatibility test, or a documented compatibility matrix checked in CI.

6. **Targeted live validation (non-blocking but strongly recommended)**
   - Run at least one real Planner validation on a sufficiently long PRD known to stress the previous design.
   - Success signal: the Planner obeys the exact active output directory and does not emit valid run artifacts outside that location.

### Quality Goal
Make Planner startup context assembly robust enough that the concrete artifact-generation contract remains mechanically salient even when the underlying PRD is long.

The output of this PRD should be a proven Planner reference implementation of the startup-envelope architecture that can later be reused by other roles without having to redesign the pattern from scratch.

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/leio-sdlc/scripts/spawn_planner.py`
- `/root/projects/leio-sdlc/playbooks/planner_playbook.md`
- `/root/projects/leio-sdlc/tests/test_spawn_planner.py`
- `/root/projects/leio-sdlc/tests/test_planner_startup_envelope.py` (new, if needed)
- `/root/projects/leio-sdlc/tests/test_planner_envelope_forward_compatibility.py` (new, if needed)
- `/root/projects/leio-sdlc/scripts/` planner-specific helper(s) for startup-envelope assembly/rendering (new, only if needed and strictly limited to Planner scope)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial `ISSUE-1183` investigation focused on the visible symptom that Planner PR contracts landed in `docs/PRs/...` instead of the active `.sdlc_runs/...` job directory.
- **v1.1 evidence upgrade**: Runtime diagnostics proved the orchestrator and `spawn_planner.py` path chain were already computing and passing the correct `run_dir/out_dir/job_dir` contract.
- **v1.2 architectural conclusion**: The root cause was reframed from “Planner path bug” to “Planner startup-prompt architecture failure,” because the concrete `create_pr_contract.py --job-dir ...` command was buried late inside a very long startup prompt.
- **v1.3 scope decision**: The design discussion rejected an all-agent mega-PRD. The approved direction is Planner-first but architecturally complete: implement the new startup-envelope pattern on Planner only, then reuse that pattern later for other roles under separate follow-up issues / PRDs.
- **v1.4 external-best-practice alignment**: Industry context-engineering guidance reinforced the same direction: front-load short high-priority instructions, separate contract from long references, prefer progressive disclosure, and make context assembly observable.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`planner_startup_envelope_top_level_keys`**:
```text
execution_contract
reference_index
final_checklist
```

- **`planner_forbidden_top_level_field`**:
```text
task_brief
```

- **`planner_execution_contract_required_read_clause`**:
```text
Before producing any artifact, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.
```

- **`planner_execution_contract_scaffold_clause`**:
```text
You MUST FIRST create each PR contract by calling `python3 {contract_script} --only-scaffold --workdir {workdir} --job-dir {out_dir} --title <title>` before writing contract content.
```

- **`planner_execution_contract_output_location_clause`**:
```text
The only valid output location for PR contract artifacts in this run is `{out_dir}`.
```

- **`planner_execution_contract_invalid_outside_clause`**:
```text
Any artifact written outside the active output location is invalid for this run.
```

- **`planner_execution_contract_done_clause`**:
```text
This task is complete only when the generated PR contract files physically exist under `{out_dir}`.
```

- **`planner_rendered_prompt_section_headers`**:
```text
# EXECUTION CONTRACT
# REFERENCE INDEX
# FINAL CHECKLIST
```

- **`planner_reference_index_required_entries`**:
```json
[
  {
    "id": "authoritative_prd",
    "kind": "prd",
    "path": "<ABS_PRD_PATH>",
    "required": true,
    "priority": 1,
    "purpose": "authoritative_requirements"
  },
  {
    "id": "planner_playbook",
    "kind": "playbook",
    "path": "<ABS_PLANNER_PLAYBOOK_PATH>",
    "required": true,
    "priority": 1,
    "purpose": "planner_methodology"
  },
  {
    "id": "pr_contract_template",
    "kind": "template",
    "path": "<ABS_PR_TEMPLATE_PATH>",
    "required": true,
    "priority": 1,
    "purpose": "output_contract_shape"
  }
]
```

- **`planner_uat_mode_required_reference_entry`**:
```json
{
  "id": "uat_report",
  "kind": "uat_report",
  "path": "<ABS_UAT_REPORT_PATH>",
  "required": true,
  "priority": 1,
  "purpose": "uat_missing_requirements"
}
```

- **`planner_uat_mode_task_clause`**:
```text
Read the required references, then generate focused Micro-PR contracts only for requirements marked missing or partial in the UAT report, without replanning already-satisfied functionality.
```

- **`planner_slice_mode_insert_after_clause`**:
```text
You MUST use the exact same `--insert-after {failed_pr_id}` value for every sliced PR generated in this run.
```


- **`planner_envelope_forward_compatibility_targets`**:
```text
Auditor
Reviewer
Verifier
Coder
```

- **`planner_debug_artifact_relative_paths`**:
```text
planner_debug/startup_packet.json
planner_debug/startup_prompt.txt
planner_debug/scaffold_contract.txt
```
