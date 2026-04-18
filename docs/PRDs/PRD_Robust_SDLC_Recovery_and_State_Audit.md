---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Robust SDLC Recovery and State Audit

## 1. Context & Problem (业务背景与核心痛点)
Currently, the LEIO SDLC engine is brittle when facing external interruptions (e.g., OpenClaw Gateway restarts or SIGTERM events). 

**Systemic Assumption: Singleton Execution & Governance**
The SDLC engine operates as a strict singleton per project. Parallel execution or external manual commits are strictly prohibited during an active SDLC lifecycle. As it is difficult to distinguish SDLC commits from unauthorized external commits without complex tracking, the engine follows the **"Singleton Sovereignty"** principle: All commits merged between the `baseline_commit` and the current `HEAD` are assumed to belong to the SDLC run. Any unauthorized external commits during this window are a violation of governance, are NOT protected, and will be overwritten during a withdrawal to ensure system integrity.

**Core Pain Points:**
1.  **Resume Failure (ISSUE-1154)**: The `get_next_pr.py` script relies on fragile Regex and fails to recognize `status: in_progress`. If a process is killed while a PR is running, the resume logic skips it, incorrectly reports the queue as empty, and signals a false success.
2.  **Conservative Guardrails**: The "Dirty Workspace" check blocks resumption even if the changes belong to the interrupted task, forcing manual intervention.
3.  **No Safe Undo**: There is no automated way to withdraw a PRD run without manually parsing hashes or risking a blind overwrite of shared history.
4.  **Metadata Blindness**: The engine does not verify the integrity of critical recovery markers (like `baseline_commit.txt`) before starting, leading to non-deterministic failures.

## 2. Requirements & User Stories (需求定义)
- **REQ-1 (Checkpoint Recovery)**: Implement a unified `--resume` flag that identifies the interrupted PR, resets its state, cleans up the local workspace, and restarts the task from its stable checkpoint.
- **REQ-2 (Atomic State Restoration)**: Implement a `--withdraw` flag that utilizes `baseline_commit.txt` to atomically and idempotently restore the repository to its baseline state, ensuring 100% fidelity regardless of intermediate merge history.
- **REQ-3 (Pre-flight Sanity Audit)**: Introduce a mandatory "Healthy Check" on startup to verify if critical recovery metadata is intact.
- **REQ-4 (Structured State Resolution)**: Replace Regex-based status detection with a robust YAML Frontmatter parser for 100% deterministic state tracking.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 The Startup Sanity Audit (The Healthy Check)
Before entering the state machine, the orchestrator MUST build a `SanityContext`:
1.  **Metadata Check**: Verify that `baseline_commit.txt` and the `job_dir` exist. If missing during a resume/withdraw attempt, the engine must fail with a `[FATAL_METADATA]` error.
2.  **Branch Check**: If in a branch, verify it matches the current PRD's naming convention.
3.  **Stability Check**: Verify the current Git HEAD is reachable from the baseline hash.

### 3.2 Logic for --resume (Checkpoint-based Task Restart)
If `--resume` is provided:
1.  **Context Discovery**: The orchestrator utilizes the `StructuredStateParser` to scan the job directory.
2.  **Workspace Purification (PRE-CONDITION)**: If the workspace is dirty: Execute the `--cleanup` logic (Stage everything -> WIP Commit -> Rename branch -> Checkout master). This MUST be done before modifying any metadata to preserve the broken state.
3.  **State Reset (MANDATORY)**: If any PR is found in `in_progress` state, its YAML frontmatter MUST be reset to `status: open`.
4.  **Task Re-ignition**: Set `force_replan = false` internally and proceed to `State 0`.

### 3.3 Atomic Withdrawal (Target Tree Snapshot with Audit)
If `--withdraw` is provided:
1.  **Safety Check**: Verify the user is on `master/main`.
2.  **Lineage Audit (Non-blocking)**: 
    - Execute `git log {baseline_hash}..HEAD --oneline`.
    - If non-SDLC commits exist, output a **GOVERNANCE WARNING** log.
3.  **Workspace Purification**: Reuse the `--resume` logic to safely stage and quarantine any dirty state into a WIP commit and isolated branch. This MUST be done before the hard reset to prevent data loss.
4.  **State Capture**: Capture current HEAD hash as `{interrupted_hash}`.
5.  **Baseline Retrieval**: Read `baseline_commit.txt` to get `{baseline_hash}`.
6.  **Target Tree Snapshot Restoration (Force Baseline Alignment)**: 
    - Execute `git reset --hard {baseline_hash}`.
    - Execute `git reset --soft {interrupted_hash}`.
    - **Idempotency Guard**: Execute `git diff --cached --quiet`. Only if changes exist, proceed.
    - Execute `git commit -m "chore: force baseline alignment of PRD {prd_name} to baseline"`.
7.  **Job Teardown**: Mark the PRD job directory with the `.withdrawn` suffix.

### 3.4 Structured YAML Frontmatter Parser
Refactor `get_next_pr.py` and `update_pr_status.py` to use a dedicated parser utility:
1.  **Boundary Enforcement**: Strictly extract content between the first `---` block.
2.  **Schema Alignment**: Map the `status` field to the machine states: `open`, `in_progress`, `closed`, `blocked`.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Recovery from Crash**
  - **Given** an interrupted SDLC run where a PR is `status: in_progress`.
  - **When** `orchestrator.py --resume` is executed.
  - **Then** the PR status is reset to `open`, the workspace is purified, and the task restarts.

- **Scenario 2: Force Baseline Alignment**
  - **Given** a partially completed PRD run with both SDLC and unauthorized external commits merged.
  - **When** `orchestrator.py --withdraw` is executed.
  - **Then** the repository is restored to the baseline state via a single atomic commit, overwriting all intermediate changes.
  - **And** a governance violation warning is logged.

- **Scenario 3: Missing Metadata Guardrail**
  - **Given** a resume command but `baseline_commit.txt` is missing.
  - **When** the orchestrator starts.
  - **Then** it must output the `Handoff_Metadata_Missing` error and stop.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **State Transition Testing**: Verify YAML parsing accuracy using unit tests.
- **Idempotency Simulation**: Mock a scenario where withdrawal is triggered twice and ensure the system remains Clean and stable without failing.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`: Main entry logic for resume/withdraw/sanity.
- `scripts/get_next_pr.py`: Refactored to use structured parser.
- `scripts/update_pr_status.py`: Refactored to use structured parser.
- `scripts/rollback.sh`: (Reference) Ensure standard guardrails are applied.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL - STRING DETERMINISM]**

```markdown
- Handoff_Metadata_Missing: "[FATAL_METADATA] Critical SDLC anchors (baseline_commit.txt) are missing. Automatic recovery is impossible. You must manually verify the repository state or use --force-replan true."
- Governance_Warning: "[WARNING] Unauthorized external commits detected between baseline and HEAD. These changes are NOT protected by SDLC and will be overwritten to ensure baseline integrity."
- YAML_States: ["status: open", "status: in_progress", "status: closed", "status: blocked"]
- Directory_Markers: [".withdrawn", ".sdlc_runs"]
- Rollback_Message: "chore: force baseline alignment of PRD {prd_name} to baseline"

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.1**: Transition from "Human-Managed Recovery" to "Systemic Self-Healing". This version introduces robust, idempotent recovery mechanisms and a clear governance model for handling interruptions and rollbacks.
- Placeholders: ["{baseline_hash}", "{interrupted_hash}", "{prd_name}"]
```
