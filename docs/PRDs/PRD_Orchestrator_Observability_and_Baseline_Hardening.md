---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Orchestrator Observability and Baseline Hardening

## 1. Context & Problem (业务背景与核心痛点)

Two runtime gaps were identified during SDLC execution of `PRD_Planner_Startup_Envelope_Refactor` and `PRD_OpenClaw_CLI_Compatibility_Audit_and_Runtime_Hardening`:

### Gap A: Preflight Failure Visibility
The orchestrator correctly runs `preflight.sh` BEFORE the Reviewer (line 882 of `orchestrator.py`). However, when preflight fails, the only action is `system_alert_text = f"Preflight failed:\n..."; continue` — there is **no user-visible notification**. The orchestrator silently loops back to Coder, which to an external observer looks like Coder is stuck in an infinite retry loop with no explanation. This created confusion during PR-003 of the Planner Envelope PRD, where the user saw repeated "Coder → Coder → Coder" cycles without any indication that preflight was the actual gate.

### Gap B: Baseline Anchor Created Too Late
`baseline_commit.txt` is currently written at line 655 of `orchestrator.py`, AFTER State 0 slicing succeeds and PR files are detected. If the Planner process crashes during slicing (which happens when the orchestrator subprocess is killed by model changes, gateway restarts, or resource limits), the baseline anchor is never created. This makes `--resume` and `--withdraw` inoperable because they both depend on `baseline_commit.txt` existing in the job directory.

## 2. Requirements & User Stories (需求定义)

1. **Preflight failure must produce a user-visible notification**
   - When `preflight.sh` returns non-zero, the orchestrator must send a `notify_channel` message before re-spawning the Coder
   - The notification must include: which PR failed, the current attempt count, and the retry limit

2. **Baseline anchor must be created before Planner execution**
   - `baseline_commit.txt` must be written immediately after `job_dir` and `run_dir` are resolved, before `spawn_planner.py` is invoked
   - A minimal `run_manifest.json` should be co-created with the baseline commit hash, PRD path, and run timestamp

3. **Do NOT change the flow order**
   - Preflight already runs before Reviewer; this PRD must not alter the state machine ordering
   - This PRD is purely about observability and robustness hardening

4. **Single-file change**
   - All modifications are confined to `scripts/orchestrator.py`
   - No changes to `agent_driver.py`, `spawn_planner.py`, `spawn_coder.py`, `spawn_reviewer.py`, `merge_code.py`, or playbooks

## 3. Architecture & Technical Strategy (架构设计与技术路线)

- **Target File**: `scripts/orchestrator.py`
- **Strategy**: Inject notifications and move anchor creation timing without touching the state machine logic
- **Preflight notification**: Insert `notify_channel` at line ~890 (before `continue`), format the retry count
- **Baseline anchor**: Move the `baseline_commit.txt` write block from line 655 to after `job_dir` resolution (~line 430-500), add `run_manifest.json` co-write
- **No structural changes**: The state machine states (0-6), the `switch`/`case` logic, and the loop structure remain untouched

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** Preflight failure sends visible notification
  - **Given** Coder has produced code for a PR and preflight.sh exists
  - **When** preflight.sh returns non-zero exit code
  - **Then** the orchestrator sends a notification to the channel containing "Preflight failed", the PR identifier, and the current retry count
  - **And** the orchestrator continues to re-spawn the Coder with the system alert

- **Scenario 2:** Baseline anchor exists before Planner runs
  - **Given** the orchestrator has resolved `job_dir` and `run_dir`
  - **When** the orchestrator transitions to State 0 (Auto-slicing)
  - **Then** `baseline_commit.txt` already exists in `job_dir` containing the current HEAD commit hash
  - **And** `run_manifest.json` exists in `run_dir` containing the PRD path and run timestamp

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- Use a mock environment with `SDLC_TEST_MODE=true` to verify preflight failure notification without real agent invocations
- Verify baseline anchor creation by spawning the orchestrator with a dummy PRD and checking existence of `baseline_commit.txt` and `run_manifest.json` BEFORE planner would be invoked
- The primary quality risk is accidentally breaking the orchestrator's state machine — mitigate by keeping changes minimal and surface-level
- Validate that `--resume` works after a simulated crash that occurs during State 0 slicing

## 6. Framework Modifications (框架防篡改声明)

- `scripts/orchestrator.py`

## 7. Hardcoded Content (硬编码内容)

### Preflight failure notification format:
```text
❌ Preflight failed for {base_filename} (attempt {orch_yellow_counter}/{yellow_retry_limit}). Retrying Coder...
```

### run_manifest.json format:
```json
{
    "baseline_commit": "<git HEAD hash>",
    "prd_path": "<absolute PRD path>",
    "job_dir": "<absolute job_dir>",
    "run_dir": "<absolute run_dir>",
    "started_at": "<ISO 8601 timestamp>"
}
```
