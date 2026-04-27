---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Coder Startup Envelope Migration

## 1. Context & Problem (业务背景与核心痛点)

### 1.1 Background

`leio-sdlc` has now completed the startup-envelope migration for Planner, Reviewer, and Auditor. Those three roles no longer rely on oversized first-turn prompt assembly that inlines long document bodies. Instead, they use a contract-first startup packet assembled by `scripts/envelope_assembler.py`, with persisted debug artifacts for post-mortem inspection.

Coder is now the largest remaining startup-path outlier.

### 1.2 Current Coder Architecture

`spawn_coder.py` still uses monolithic prompt assembly through `build_prompt()` and `config/prompts.json` for three separate execution paths:

1. **Initial execution** via `prompts.json["coder"]`
2. **Revision loop** via `prompts.json["coder_revision"]`
3. **System alert recovery** via `prompts.json["coder_system_alert"]`

The initial path inlines:
- full coder playbook text,
- full PR contract body,
- full PRD body.

The revision path appends an additional revision prompt string, and the system-alert path appends a separate corrective-action prompt string. If a revision is requested but `.coder_session` is missing, the current implementation reboots by concatenating the initial prompt with the revision prompt, which is a fragile string-level fallback rather than an explicit startup protocol.

### 1.3 Why Coder Is Harder Than Reviewer/Auditor

Coder is not a one-shot evaluation agent. It is a **stateful execution role** with:
- persistent session continuity through `.coder_session`,
- revision-loop re-entry after Reviewer rejection,
- system-alert corrective execution after preflight/git failures,
- branch-isolation and clean-workspace constraints,
- strong completion semantics (`tests/preflight green + explicit commit + clean git status + latest hash report`).

That means a partial migration of only the initial startup prompt would leave the highest-risk Coder behaviors on the legacy path.

### 1.4 Core Pain Points

1. **Instruction burial in the initial startup path**
   - The first-turn prompt mixes workspace constraints, playbook methodology, PR contract body, and PRD body in one large blob.
   - The Coder may form a loose high-level impression before it sees the most important execution constraints.

2. **Split-brain startup architecture across modes**
   - Initial, revision, and system-alert flows use different prompt sources and different assembly patterns.
   - The role is not governed by a single structured startup protocol.

3. **Fragile session-loss fallback**
   - If feedback arrives but `.coder_session` is missing, the system falls back to string concatenation of the initial and revision prompts instead of an explicit bootstrap mode.

4. **Poor forensic observability for revision loops**
   - We cannot reliably inspect what exact startup payload was sent for the initial run vs. each revision or system-alert injection.
   - This makes debugging drift, non-action acknowledgments, and session bootstrap failures slower than necessary.

5. **Playbook assumes monolithic-prompt era behavior**
   - `playbooks/coder_playbook.md` still assumes the task context is effectively preloaded in the first-turn prompt.
   - After migration, the playbook must explicitly align with contract-first startup, required reference reads, and mode-aware behavior.

### 1.5 Decision From Copilot Discussion

We explicitly choose **full migration (Plan B)**:
- migrate **initial + revision + system_alert** together,
- introduce an explicit **revision_bootstrap** mode for session-loss recovery,
- minimally update the coder playbook where it conflicts with or fails to describe the new startup protocol.

### 1.6 Explicitly Not in Scope

- Reviewer, Auditor, Planner, Verifier, Arbitrator, or Manager startup-path refactors
- redesigning `invoke_agent()` transport or temp-file handling
- changing Coder branch/push policy
- changing Reviewer JSON schema
- changing Orchestrator business state-machine semantics beyond compatibility glue strictly required for the new Coder startup protocol
- large-scale rewrite of coder methodology beyond startup-protocol alignment

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Unify all Coder startup modes under `envelope_assembler.py`**
   - `spawn_coder.py` must stop using `build_prompt("coder")`, `build_prompt("coder_revision")`, and `build_prompt("coder_system_alert")` for production startup behavior.
   - The Coder startup path must support these explicit modes:
     - `initial`
     - `revision`
     - `system_alert`
     - `revision_bootstrap`

2. **Initial mode must be contract-first and reference-index-driven**
   - The first-turn startup payload must no longer inline the full PRD body, full PR contract body, or full coder playbook body.
   - These documents must be referenced through the startup packet and read on demand.

3. **Revision mode must become a structured startup packet**
   - Reviewer feedback must no longer be attached through a legacy prompt template.
   - The revision path must use the same envelope architecture, with the feedback artifact treated as a required reference and/or explicit contract input.

4. **System-alert mode must become a structured startup packet**
   - Preflight/git/system-alert corrective work must no longer use a separate legacy template path.
   - The Coder must receive a structured corrective-action startup contract.

5. **Session-loss fallback must become explicit `revision_bootstrap`**
   - If a revision is requested and `.coder_session` is missing, `spawn_coder.py` must create a new Coder session using a dedicated bootstrap mode.
   - This mode must preserve revision semantics without relying on ad hoc prompt-string concatenation.

6. **Session continuity must be preserved**
   - When `.coder_session` exists, revision and system-alert flows must continue using the existing session key.
   - When a new session is created, `.coder_session` must still be updated with the active session key.

7. **Minimal but explicit playbook update is in scope**
   - `playbooks/coder_playbook.md` must be updated only where necessary to align with the new architecture.
   - The updated playbook must explicitly define:
     - contract-first priority,
     - required reference-read behavior,
     - mode-aware execution expectations,
     - revision anti-acknowledgment rule,
     - system-alert completion expectations.

8. **Observability artifacts are mandatory for all Coder modes**
   - The startup packet and rendered prompt must be persisted for:
     - initial startup,
     - each revision,
     - each system alert,
     - each revision bootstrap.
   - Artifacts must be mode-distinguishable and must not overwrite each other across the same run.

9. **Backward compatibility for orchestrator invocation shape must be preserved**
   - `orchestrator.py` may continue invoking `spawn_coder.py` with:
     - `--feedback-file`
     - `--system-alert`
     - `--run-dir`
   - The internal interpretation of these flags may change, but the CLI contract must remain stable unless this PRD explicitly authorizes otherwise.

10. **Prompt deprecation must be completed for legacy Coder startup entries**
   - `config/prompts.json` entries for:
     - `coder`
     - `coder_revision`
     - `coder_system_alert`
     must be replaced with deprecation markers.
   - They must no longer contain the old startup logic.

### 2.2 Non-Functional Requirements

1. The initial Coder startup prompt must be materially shorter than the current monolithic prompt.
2. Revision and system-alert startup payloads must become inspectable artifacts instead of implicit string concatenation behavior.
3. The migration must preserve stateful session behavior and must not degrade the existing revision loop UX.
4. The solution must be role-agnostic enough that future Verifier/Arbitrator migrations do not require changing the top-level envelope shape.
5. The migration must reduce context drift in revision loops by making reviewer findings a first-class startup reference rather than incidental appended text.

### 2.3 User Stories

- As the Manager, I want the Coder startup payload to be contract-first so the most important execution constraints are not buried under long documents.
- As the Manager, I want revision re-entry to use the same structured protocol as initial execution so the Coder behaves consistently across loops.
- As the Manager, I want session-loss recovery to be explicit and auditable so I can debug why a new session was created.
- As the Architect, I want the coder playbook to describe the new startup protocol clearly so the behavior contract lives in one durable place.
- As the Auditor, I want the Coder startup artifacts persisted per mode so I can inspect the exact startup context that led to a bad run.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Target Design

This migration upgrades `spawn_coder.py` from a prompt-concatenation script into a **mode-aware envelope dispatcher**.

The resulting architecture must look like:

```text
orchestrator.py
  -> spawn_coder.py
       -> envelope_assembler.py (role="coder", mode=initial|revision|system_alert|revision_bootstrap)
       -> invoke_agent()
```

### 3.2 Required Coder Modes

#### A. `initial`
Used when starting work on a PR for the first time.

Required references:
- PR contract file
- PRD file
- coder playbook path

Execution contract must explicitly include:
- locked workdir,
- branch-isolation rule,
- no push / no branch switching rule,
- required test/preflight expectations,
- explicit commit requirement,
- clean git status requirement,
- latest hash reporting requirement.

#### B. `revision`
Used when Reviewer feedback arrives and `.coder_session` exists.

Required references:
- PR contract file
- PRD file
- coder playbook path
- feedback artifact file

Execution contract must explicitly include:
- reviewer findings are actionable work, not acknowledgement-only context,
- the Coder must modify code, run tests/preflight, commit, and leave the workspace clean,
- revision work must stay anchored to Reviewer findings and the PR contract.

#### C. `system_alert`
Used when the Orchestrator sends corrective action after preflight, git hygiene, or similar system-level failure.

Required references:
- PR contract file
- PRD file
- coder playbook path

Execution contract must explicitly include:
- exact alert text,
- corrective-action semantics,
- completion condition = required fixes implemented, tests/preflight green, explicit commit done if code changed, workspace clean.

#### D. `revision_bootstrap`
Used when feedback exists but `.coder_session` is missing.

Required references:
- PR contract file
- PRD file
- coder playbook path
- feedback artifact file

This mode must behave like a revision run, but as a clean new session bootstrap rather than an append-to-existing-session operation.

### 3.3 Envelope Structure for Coder

`envelope_assembler.py` must be extended to support `role="coder"` with the same top-level shape already used by other migrated roles:
- `execution_contract`
- `reference_index`
- `final_checklist`

The top-level packet shape must remain consistent with the existing envelope architecture.

### 3.4 Artifact Persistence Strategy

Unlike Reviewer/Auditor, Coder may emit multiple startup packets in a single run. Therefore, artifact persistence must be mode-aware and non-overwriting.

Approved artifact layout:

```text
{run_dir}/coder_debug/initial/startup_packet.json
{run_dir}/coder_debug/initial/rendered_prompt.txt
{run_dir}/coder_debug/revision_001/startup_packet.json
{run_dir}/coder_debug/revision_001/rendered_prompt.txt
{run_dir}/coder_debug/system_alert_001/startup_packet.json
{run_dir}/coder_debug/system_alert_001/rendered_prompt.txt
{run_dir}/coder_debug/revision_bootstrap_001/startup_packet.json
{run_dir}/coder_debug/revision_bootstrap_001/rendered_prompt.txt
```

Mode counters must be deterministic within a run directory. Repeated revision or system-alert events must increment rather than overwrite.

### 3.5 Playbook Alignment Strategy

`playbooks/coder_playbook.md` must be minimally updated to reflect the new startup protocol:

1. **Contract-first priority**
   - The execution contract is authoritative over general prose.

2. **Required reference-read rule**
   - Before coding, the Coder must read all `required=true` and `priority=1` references.

3. **Mode awareness**
   - The playbook must explicitly explain initial, revision, system_alert, and revision_bootstrap behavior.

4. **Revision anti-acknowledgment rule**
   - Revision work is execution work, not a conversational acknowledgement step.

5. **System-alert exit criteria**
   - Corrective action is complete only when the workspace is healthy again, not when the alert has merely been read.

This is a targeted protocol-alignment update, not a methodology rewrite.

### 3.6 `spawn_coder.py` Refactor Scope

`spawn_coder.py` must be refactored to:
- assemble envelopes instead of inlining startup text,
- preserve branch guardrails,
- preserve API key assignment and engine/model environment wiring,
- preserve `.coder_session` behavior,
- preserve existing CLI flags,
- route feedback and system alerts through explicit modes,
- replace prompt-string concatenation fallback with `revision_bootstrap`.

### 3.7 `config/prompts.json` Cleanup

The following keys must be deprecated and must no longer be used for startup behavior:
- `coder`
- `coder_revision`
- `coder_system_alert`

### 3.8 Orchestrator Compatibility Rule

`orchestrator.py` is not the primary target of this PRD. However, compatibility adjustments are allowed if strictly required so the new Coder startup architecture can be exercised without changing the upstream orchestrator CLI behavior.

### 3.9 Non-Goals

This PRD does **not** authorize:
- changing the branch lifecycle model,
- changing Reviewer schema contracts,
- redesigning `invoke_agent()` transport,
- migrating Verifier/Arbitrator/Manager,
- broad playbook prose rewrites unrelated to startup-protocol alignment.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Initial startup creates durable startup artifacts and a reusable coder session**
  - **Given** a valid PR contract, a valid PRD, a clean feature branch, and no pre-existing `.coder_session`
  - **When** `spawn_coder.py` is invoked for a first-time coding run
  - **Then** a coder session key is created and persisted to `{run_dir}/.coder_session`
  - **And** the run directory contains the exact initial startup artifacts under:
    - `{run_dir}/coder_debug/initial/startup_packet.json`
    - `{run_dir}/coder_debug/initial/rendered_prompt.txt`
  - **And** the startup packet artifact contains references to the PR contract path, PRD path, and coder playbook path

- **Scenario 2: Revision reuses the existing coder session and records a revision artifact**
  - **Given** an existing `{run_dir}/.coder_session` file and a reviewer feedback artifact
  - **When** `spawn_coder.py --feedback-file <feedback>` is invoked
  - **Then** the value stored in `{run_dir}/.coder_session` remains the active session key for the run
  - **And** a new revision artifact directory is created at `{run_dir}/coder_debug/revision_001/`
  - **And** that directory contains both `startup_packet.json` and `rendered_prompt.txt`
  - **And** the revision startup packet records the reviewer feedback artifact as required execution context

- **Scenario 3: Revision bootstrap recovers cleanly when the session file is missing**
  - **Given** a reviewer feedback artifact and no `{run_dir}/.coder_session` file
  - **When** `spawn_coder.py --feedback-file <feedback>` is invoked
  - **Then** a new coder session key is created and persisted to `{run_dir}/.coder_session`
  - **And** the run directory contains a bootstrap artifact directory at `{run_dir}/coder_debug/revision_bootstrap_001/`
  - **And** that directory contains both `startup_packet.json` and `rendered_prompt.txt`
  - **And** the bootstrap startup packet records the reviewer feedback artifact as required execution context

- **Scenario 4: System alert produces a distinct corrective-action startup artifact**
  - **Given** a valid PR contract, a valid PRD, an active coder session, and a system alert string from the orchestrator
  - **When** `spawn_coder.py --system-alert <alert>` is invoked
  - **Then** the active coder session remains available for continued work
  - **And** the run directory contains a corrective-action artifact directory at `{run_dir}/coder_debug/system_alert_001/`
  - **And** that directory contains both `startup_packet.json` and `rendered_prompt.txt`
  - **And** the startup packet records the exact alert text as part of the corrective-action contract

- **Scenario 5: Multiple mode transitions preserve distinct, non-overwriting audit artifacts**
  - **Given** a coder run that experiences more than one revision or more than one system alert in the same run directory
  - **When** those transitions occur sequentially
  - **Then** each event produces its own incremented artifact directory (for example `revision_001`, `revision_002`, `system_alert_001`)
  - **And** earlier artifact directories remain intact rather than being overwritten by later transitions

- **Scenario 6: Orchestrator retry and resume flows remain operational with the migrated coder startup protocol**
  - **Given** the orchestrator invokes `spawn_coder.py` through normal start, reviewer-feedback retry, or system-alert recovery paths
  - **When** a sandboxed SDLC run is executed end-to-end
  - **Then** the run can progress through coder startup, coder retry, reviewer handoff, and subsequent pipeline states without requiring any new orchestrator CLI flags
  - **And** the expected coder startup artifacts are present in the active run directory for each exercised mode

- **Scenario 7: The migrated coder path still satisfies manager-visible completion semantics**
  - **Given** a Coder task completes successfully in any of the supported modes
  - **When** the Coder hands control back to the orchestrator
  - **Then** the workspace is left in a reviewable state with a persisted coder session key, a recorded latest commit hash available from git, and mode-specific startup artifacts present in the run directory

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk

The primary risk is **stateful protocol drift**:
- initial mode might migrate successfully while revision/system-alert silently remain legacy,
- session-loss fallback might regress into inconsistent startup behavior,
- artifact persistence might overwrite previous revision evidence,
- playbook and envelope contract might contradict one another.

### 5.2 Testing Strategy

1. **Unit tests for envelope assembly**
   - Validate coder mode handling in `envelope_assembler.py`
   - Validate required references and execution-contract fields per mode
   - Validate mode-aware artifact output paths

2. **Unit tests for `spawn_coder.py` routing**
   - initial path
   - revision path with existing session
   - revision bootstrap path with missing session
   - system-alert path

3. **Prompt-deprecation tests**
   - Ensure `prompts.json` no longer contains active startup logic in `coder`, `coder_revision`, `coder_system_alert`

4. **Compatibility tests with orchestrator invocation shape**
   - Ensure existing `--feedback-file` and `--system-alert` routes still work

5. **Mocked integration tests**
   - Run mocked coder flows to validate artifact persistence and mode transitions without live model dependency

6. **Minimal end-to-end sandbox validation**
   - At least one sandboxed SDLC run must prove that a Coder startup can enter a normal code-review loop after the migration

### 5.3 Quality Goal

After this migration, Coder must become a first-class envelope-driven role with no remaining legacy startup-prompt dependence for its initial, revision, or system-alert paths.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_coder.py`
- `scripts/envelope_assembler.py`
- `playbooks/coder_playbook.md`
- `config/prompts.json`
- `tests/test_spawn_coder.py`
- `tests/test_spawn_coder_refactor.py`
- `tests/test_envelope_assembler.py`
- `tests/test_coder_revision_prompts.py`
- `tests/test_orchestrator.py` (compatibility-only changes if strictly required)
- mocked or sandboxed coder-flow tests that must be updated to reflect the new startup protocol

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft based on the explicit decision to choose Plan B: migrate `initial + revision + system_alert` together and add an explicit `revision_bootstrap` mode.
- **Audit Rejection (v1.0)**: Rejected because Section 4 used white-box acceptance checks (source inspection and implementation-audit assertions) instead of pure black-box observable behavior.
- **v2.0 Revision Rationale**: Preserve the architecture unchanged and rewrite only the acceptance contract so each scenario is provable from observable session behavior, run-directory artifacts, and sandbox pipeline outcomes.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Mode Names

```text
initial
revision
system_alert
revision_bootstrap
```

### Exact Artifact Layout

```text
{run_dir}/coder_debug/initial/startup_packet.json
{run_dir}/coder_debug/initial/rendered_prompt.txt
{run_dir}/coder_debug/revision_001/startup_packet.json
{run_dir}/coder_debug/revision_001/rendered_prompt.txt
{run_dir}/coder_debug/system_alert_001/startup_packet.json
{run_dir}/coder_debug/system_alert_001/rendered_prompt.txt
{run_dir}/coder_debug/revision_bootstrap_001/startup_packet.json
{run_dir}/coder_debug/revision_bootstrap_001/rendered_prompt.txt
```

### Exact `prompts.json` Deprecation Markers

- **`coder`**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py
```

- **`coder_revision`**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py
```

- **`coder_system_alert`**:
```text
__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py
```

### Exact Playbook Behavioral Clauses To Preserve In Meaning

- **Revision anti-acknowledgment rule**:
```text
Revision work is execution work, not acknowledgment work.
```

- **System-alert completion rule**:
```text
A system alert is not resolved when it is acknowledged; it is resolved only when the required corrective action is completed and the workspace is healthy again.
```
