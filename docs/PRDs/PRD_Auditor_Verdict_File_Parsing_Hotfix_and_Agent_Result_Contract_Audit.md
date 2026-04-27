---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Auditor Verdict File Parsing Hotfix and Result-Contract Regression Coverage

## 1. Context & Problem (业务背景与核心痛点)

### 1.1 Background

`leio-sdlc` recently migrated Auditor, Reviewer, and Planner startup flows to the envelope-based startup protocol. Under the new Auditor startup path, the contract explicitly instructs the agent to write its structured verdict to a file (`auditor_verdict.json`) via `contract_params.output_file`.

A real production run on 2026-04-27 exposed a critical regression: the Auditor correctly wrote an `APPROVED` verdict to `auditor_verdict.json`, but `spawn_auditor.py` still tried to determine status only from `stdout`. Because the new envelope-driven Auditor no longer guarantees JSON on stdout, the script fell through to `UNKNOWN` and emitted the Manager handoff for `REJECTED`.

This is a governance-critical defect because it can invert the outcome of the Auditor gate and mislead the Boss about whether a PRD is approved to proceed.

### 1.2 Concrete Root Cause

The current `spawn_auditor.py` behavior is inconsistent with its own startup contract:

- **Producer contract**: Auditor writes structured verdict JSON to `auditor_verdict.json`
- **Consumer implementation**: `spawn_auditor.py` parses only `result.stdout`
- **Missing logic**: there is no fallback or canonical read from the declared output file

As a result, envelope-driven file output can succeed while the Manager-facing verdict classification still fails.

### 1.3 Why This Is More Important Than Normal Feature Work

This is not a cosmetic bug and not a local role bug. It directly affects the correctness of the **Auditor approval gate**, which is one of the hard anti-YOLO governance barriers in `leio-sdlc`.

A false `REJECTED` wastes time and can block approved work.
A false `APPROVED` would be even worse, because it could allow an unaudited PRD into SDLC execution.

Therefore, the system must treat role-result contract parsing as a first-class, testable control-plane concern.

### 1.4 Manual Audit Conclusion Across Other Roles

A manager-side manual audit has already been completed before this PRD revision. That audit concluded:

- **Auditor**: confirmed broken
- **Reviewer**: aligned to file-based consumption
- **Verifier**: aligned to file-based consumption
- **Planner**: not the same bug class; success is determined by generated PR artifacts, not stdout verdict parsing
- **Coder**: not the same bug class; completion is governed by workspace/review/state-machine semantics, not a verdict file

Therefore, this PRD does **not** delegate an open-ended downstream task to “audit other agents.” Instead, it converts the completed audit conclusion into explicit regression-coverage requirements so the same class of mismatch cannot be reintroduced later.

### 1.5 Goal of This PRD

Deliver a minimal hotfix that:
1. fixes the Auditor verdict parsing regression immediately,
2. formalizes the canonical result-source rule for file-writing roles,
3. adds regression coverage that locks the already-audited Reviewer/Verifier/Planner result contracts,
4. prevents future startup-envelope migrations from silently reintroducing this class of bug.

### 1.6 Explicitly Not in Scope

- redesigning the startup envelope architecture itself
- rewriting Auditor/Reviewer/Verifier/Planner playbooks
- changing the transport layer in `invoke_agent()`
- broad refactors to role session management
- feature work unrelated to result-channel correctness
- changing Boss-facing governance semantics beyond making the verdict classification correct
- delegating a new exploratory multi-role audit task to downstream SDLC execution

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements

1. **Fix Auditor verdict classification to honor the declared output file**
   - `spawn_auditor.py` must no longer rely exclusively on `stdout`.
   - If stdout parsing fails or yields `UNKNOWN`, the script must read the canonical verdict file and parse structured JSON from it.

2. **Define the canonical result-source rule for file-writing roles**
   - For roles whose startup contract explicitly declares an output file, that file must be treated as the canonical result source for downstream classification.
   - Stdout may remain supported as a backward-compatible secondary source, but it must not be the only source.

3. **Preserve backward compatibility with legacy stdout-style runs**
   - If an older or mocked Auditor still emits valid JSON on stdout, parsing must continue to work.
   - The hotfix must not break old tests or legacy mocked flows that still rely on stdout-only output.

4. **Add regression protection for already-audited adjacent roles**
   - Reviewer, Verifier, and Planner must receive targeted tests that lock in the audited contract behavior.
   - This is regression coverage work, not a fresh exploratory audit task.

5. **Planner must be regression-protected as an artifact-driven success role**
   - The already-completed manual audit concluded that Planner is not a stdout-verdict role.
   - This PRD must add tests that lock in the rule that Planner success is determined by generated PR artifacts under the active output directory.

6. **Reviewer and Verifier must be regression-protected**
   - Their existing file-writing contracts must be verified and covered by tests so future migrations do not break consumer alignment.

7. **The fix must preserve Manager-facing handoff behavior**
   - The visible APPROVED/REJECTED manager handoff semantics must remain unchanged except that they become correct.

### 2.2 Non-Functional Requirements

1. The hotfix must be low blast radius and targeted.
2. The result-source precedence must be deterministic and documented in code/tests.
3. Test coverage must include real parsing fallbacks, not only mocked happy paths.
4. Regression coverage must encode the completed manual audit conclusion durably.

### 2.3 User Stories

- As the Boss, I want the Auditor gate to reflect the actual verdict written by the Auditor so I am not misled about whether a PRD passed review.
- As the Manager, I want file-writing roles to have a deterministic canonical result source so startup-envelope migrations do not silently break control-plane logic.
- As the Architect, I want the completed manual audit conclusion encoded into regression coverage so future migrations do not reopen the same result-channel mismatch class.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Canonical Result-Source Rule

This PRD establishes a strict control-plane rule:

- If a role's startup contract explicitly instructs the agent to write its result to a file, then that file is the **canonical and primary source of truth** for downstream classification.
- The consumer must attempt to read that file whenever it is expected to exist.
- Stdout is secondary compatibility telemetry only.
- Stdout may be used as a fallback only when the canonical file is absent, unreadable, or invalid.

### 3.2 Auditor Hotfix Strategy

`spawn_auditor.py` must be updated so that result classification follows this order:

1. Determine the canonical verdict file path from the declared startup contract (`auditor_verdict.json`)
2. If the canonical verdict file exists and is readable, parse the file content as structured JSON
3. Use the parsed `status` from the file as authoritative
4. Only if the file is absent, unreadable, or invalid, attempt to parse structured JSON from stdout as a backward-compatibility fallback
5. If stdout is used because the file path failed, the code must surface a deterministic warning or log signal so the degraded path is visible for forensics
6. If both stdout and file exist, the file verdict must still win; stdout is telemetry, not a competing authority source

### 3.3 Regression Coverage Scope Across Other Roles

The manual audit is already complete. Downstream implementation must **not** re-run a broad exploratory audit. Instead, it must encode the audit conclusion into automated protection:

#### A. Reviewer
Producer contract writes `review_report.json`.
Consumer logic already reads the file during merge/orchestrator review handling.
Required action in this PRD: add/adjust tests to lock this contract.

#### B. Verifier
Producer contract writes `uat_report.json`.
Orchestrator already reads `uat_report.json` and interprets PASS/NEEDS_FIX from the file.
Required action in this PRD: add/adjust tests to lock this contract.

#### C. Planner
Planner success is not a JSON verdict. Its practical success contract is the existence of generated PR contract markdown files under the isolated `job_dir` / `out_dir`.
Required action in this PRD: add/adjust tests to lock the rule that downstream success depends on artifact existence and queue state, not planner stdout semantics.

#### D. Coder
Coder is not a verdict-file role and is outside this bug class.
No direct code change is required for Coder in this PRD.

### 3.4 Implementation Surfaces

Primary hotfix target:
- `scripts/spawn_auditor.py`

Likely test and regression targets:
- `tests/test_spawn_auditor.py`
- `tests/test_auditor.py`
- `tests/test_orchestrator.py`
- `tests/test_spawn_verifier.py`
- `tests/test_spawn_planner.py` or equivalent planner-path tests
- any mocked/e2e tests that currently assume stdout-only Auditor success

### 3.5 Failure Modes That Must Be Covered

1. Auditor writes valid JSON file, stdout has no JSON
2. Auditor writes valid JSON file, stdout contains conversational text only
3. Auditor writes valid JSON file and stdout also contains valid JSON that agrees
4. Auditor writes valid JSON file and stdout contains conflicting verdict JSON
5. Auditor writes no file and stdout is invalid
6. Planner creates no PR artifacts despite non-empty stdout
7. Reviewer/Verifier continue to work when their file artifacts are the only trustworthy channel

### 3.6 Non-Goals

This PRD does not authorize a generic result-router framework extraction unless absolutely necessary to keep the hotfix clean. Prefer a direct targeted fix plus explicit regression coverage.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Auditor succeeds when the file contains APPROVED and stdout is non-JSON**
  - **Given** an Auditor run where stdout contains only conversational text or launch telemetry
  - **And** `auditor_verdict.json` contains valid JSON with `"status": "APPROVED"`
  - **When** the Auditor run completes
  - **Then** the Manager-facing handoff is APPROVED
  - **And** the run is not falsely classified as REJECTED

- **Scenario 2: Auditor succeeds when the file contains REJECTED and stdout is non-JSON**
  - **Given** an Auditor run where stdout contains no parseable verdict JSON
  - **And** `auditor_verdict.json` contains valid JSON with `"status": "REJECTED"`
  - **When** the Auditor run completes
  - **Then** the Manager-facing handoff is REJECTED

- **Scenario 3: Legacy stdout-only Auditor remains supported when the canonical file is unavailable**
  - **Given** an Auditor run that emits valid verdict JSON on stdout
  - **And** the canonical verdict file is absent, unreadable, or invalid
  - **When** the Auditor run completes
  - **Then** the Manager-facing handoff is classified correctly from stdout as a backward-compatible fallback

- **Scenario 4: Conflicting stdout and file verdicts use the file as canonical**
  - **Given** an Auditor run where stdout and `auditor_verdict.json` both exist but disagree
  - **When** the Auditor run completes
  - **Then** the file verdict is used as the final classification
  - **And** stdout is treated as non-authoritative telemetry
  - **And** the conflict is surfaced in a deterministic warning or log signal

- **Scenario 5: Reviewer remains aligned to file-based result consumption**
  - **Given** a Reviewer run that writes a valid `review_report.json`
  - **When** the orchestrator or merge gate evaluates the review result
  - **Then** approval/rework behavior is determined from the file artifact rather than requiring reviewer stdout semantics

- **Scenario 6: Verifier remains aligned to file-based result consumption**
  - **Given** a Verifier run that writes a valid `uat_report.json`
  - **When** the orchestrator evaluates the UAT result
  - **Then** PASS/NEEDS_FIX behavior is determined from the file artifact rather than requiring verifier stdout semantics

- **Scenario 7: Planner success remains determined by generated PR artifacts, not conversational stdout**
  - **Given** a Planner run under the startup-envelope system
  - **When** the planner completes slicing
  - **Then** downstream success is determined by the expected PR contract artifacts appearing under the active output directory
  - **And** planner stdout alone is insufficient to count the run as successful if the artifacts are missing

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk

The main risk is **control-plane channel drift**:
- the role prompt says “write result to file,”
- but the caller still trusts only stdout,
- creating silent governance failures after envelope migrations.

### 5.2 Testing Strategy

1. **Targeted Auditor parsing tests**
   - file-first success
   - file-first rejection
   - file-present + conflicting-stdout handling
   - file-absent + stdout-only legacy fallback
   - file-unreadable/file-invalid + stdout fallback
   - missing-file + invalid-stdout failure path

2. **Contract-alignment regression tests for Reviewer and Verifier**
   - prove that review/UAT classification still comes from artifacts

3. **Planner contract regression tests**
   - prove that generated PR file existence, not planner chatter, is the success condition

4. **Mocked integration tests**
   - simulate envelope-driven runs where stdout is non-JSON but file artifacts are correct

5. **At least one sandbox validation for Auditor hotfix**
   - prove the fixed Auditor can classify a file-written verdict correctly end to end

### 5.3 Quality Goal

After this hotfix, no migrated file-writing role may have a consumer that relies only on stdout when the startup contract says the authoritative result is written to an artifact.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_auditor.py`
- `tests/test_spawn_auditor.py`
- `tests/test_auditor.py`
- `tests/test_orchestrator.py` (only if required for result-contract alignment coverage)
- planner/reviewer/verifier result-contract tests that need explicit strengthening

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Hotfix PRD created after confirming a real envelope-era regression in `spawn_auditor.py`, plus Boss instruction to sweep other roles — especially Planner — for the same mismatch class.
- **Audit Rejection (v1.0)**: N/A yet.
- **v2.0 Revision Rationale**: Manual audit completed by the manager. PRD narrowed so downstream execution only fixes Auditor and adds regression coverage for Reviewer/Verifier/Planner, instead of delegating an open-ended multi-role audit task.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Manual Audit Conclusion

```text
Auditor: same-class bug confirmed and must be fixed.
Reviewer: no same-class bug found; add regression coverage.
Verifier: no same-class bug found; add regression coverage.
Planner: no same-class bug found; lock artifact-driven success with regression coverage.
Coder: not part of this bug class.
```

### Exact Auditor Verdict Filename

```text
auditor_verdict.json
```

### Exact Canonical Result-Source Rule

```text
If a role's startup contract explicitly instructs the agent to write its result to a file, then that file is the canonical and primary source of truth for downstream classification. The consumer must attempt to read that file whenever it is expected to exist. Stdout is secondary compatibility telemetry only and may be used as fallback only when the canonical file is absent, unreadable, or invalid.
```
