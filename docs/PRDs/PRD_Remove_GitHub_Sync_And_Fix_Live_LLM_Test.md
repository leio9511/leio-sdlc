---
Affected_Projects: [leio-sdlc]
---

# PRD: Remove_GitHub_Sync_And_Fix_Live_LLM_Test

## 1. Context & Problem (业务背景与核心痛点)

**ISSUE-1120 - Remove GitHub Sync Mock:**
`orchestrator.py` contains a `trigger_github_sync()` function that calls a mock `sync.py` script. The script is a stub that does nothing — it just writes a line to a log file and returns 0. Every time a Micro-PR is merged, Orchestrator notifies Slack with "Synchronizing code to GitHub..." and "GitHub sync complete." — but no actual `git push` ever happens. This is misleading and creates noise. The function and all its invocations should be removed entirely.

**ISSUE-1123 - Fix Live LLM E2E Test Assertion:**
`scripts/e2e/live_llm/e2e_test_triad_planner.sh` fails when run via `preflight.sh --live-llm`. The test searches for a generated PR file using a hardcoded pattern `PR_1_PL-999.md`, but `spawn_planner.py` actually generates files named `PR_Slice_1.md`, `PR_Slice_2.md`, `PR_A.md`, `PR_B.md`, etc. The assertion is wrong, causing a false-negative test failure.

## 2. Requirements & User Stories (需求定义)

### ISSUE-1120 Requirements:
- **FR-1:** Remove `trigger_github_sync()` function definition from `orchestrator.py`
- **FR-2:** Remove all calls to `trigger_github_sync()` from `orchestrator.py`
- **FR-3:** Remove all related Slack notification strings (`"Synchronizing code to GitHub..."`, `"GitHub sync complete."`, `"GitHub sync failed..."`) from `orchestrator.py`
- **FR-4:** Confirm no other code paths reference `trigger_github_sync`

### ISSUE-1123 Requirements:
- **FR-5:** Update `scripts/e2e/live_llm/e2e_test_triad_planner.sh` line ~28 to correctly locate the Planner output file
- **FR-6:** After fix, `bash preflight.sh --live-llm` should show all Live LLM E2E tests passing

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### ISSUE-1120 Technical Approach:
- **File:** `scripts/orchestrator.py`
- **Action:** Delete the `trigger_github_sync` function (lines ~195-212) and its invocation on line ~743
- **Reasoning:** The `leio-github-sync` skill is not meaningfully integrated; its `sync.py` is a no-op stub. Removing the dead code eliminates misleading UX and reduces code surface area.

### ISSUE-1123 Technical Approach:
- **File:** `scripts/e2e/live_llm/e2e_test_triad_planner.sh`
- **Action:** Replace the incorrect `ls .sdlc_runs/*/dummy_triad_prd/PR_1_PL-999.md` pattern with the correct glob pattern that matches `PR_Slice_1.md` or similar planner output. The exact pattern should be verified against the actual `spawn_planner.py` output directory structure.
- **Reference:** `spawn_planner.py` writes to `args.out_dir` which resolves to `.sdlc_runs/<target_project>/<prd_base_name>/`

### Non-Goals:
- Do NOT remove or modify `~/.openclaw/skills/leio-github-sync/` skill directory (out of scope)
- Do NOT add any replacement git push mechanism

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### Scenario 1: GitHub Sync Removal
- **Given** a running Orchestrator executing the SDLC pipeline
- **When** any Micro-PR is merged into master
- **Then** no `trigger_github_sync` function is called, no "Synchronizing code to GitHub..." message appears in Slack, and no mock sync script is invoked
- **And** `orchestrator.py` contains no reference to `trigger_github_sync`

### Scenario 2: GitHub Sync Function Removed
- **Given** the `orchestrator.py` source file
- **When** grep is run for `trigger_github_sync`
- **Then** no results are found

### Scenario 3: Live LLM E2E Test Fixed
- **Given** the Live LLM E2E test `e2e_test_triad_planner.sh`
- **When** the test is executed via `bash preflight.sh --live-llm`
- **Then** `e2e_test_triad_planner.sh` passes (exit code 0), and no "PR file not found" error appears

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Test Strategy:
- **Preflight Mocked Tests:** Run `bash preflight.sh` (default) to verify the mocked E2E suite is unaffected by the orchestrator changes. Target: 38/38 green.
- **Preflight Live LLM Tests:** Run `bash preflight.sh --live-llm` to verify the triad planner test now passes. Target: 2/2 green (both Live LLM tests).
- **Code Hygiene:** `grep -r "trigger_github_sync" scripts/orchestrator.py` should return zero matches after the fix.

### Quality Goal:
- Zero regression in existing test coverage
- Zero false-positive Slack notifications from Orchestrator
- Live LLM triad test returns to green

## 6. Framework Modifications (框架防篡改声明)

The following framework scripts are **authorized** for modification under this PRD:

- `scripts/orchestrator.py` — Remove `trigger_github_sync` function and all invocations
- `scripts/e2e/live_llm/e2e_test_triad_planner.sh` — Fix file assertion pattern

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

#### `trigger_github_sync` function to DELETE (from `orchestrator.py`):
```python
def trigger_github_sync(workdir, effective_channel, pr_id):
    sync_script = os.path.expanduser("~/.openclaw/skills/leio-github-sync/scripts/sync.py")
    if os.path.exists(sync_script):
        notify_channel(effective_channel, "Synchronizing code to GitHub...", "github_sync_start", {"pr_id": pr_id})
        try:
            res = drun([sys.executable, sync_script, "--project-dir", workdir], capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                notify_channel(effective_channel, "GitHub sync complete.", "github_sync_complete", {"pr_id": pr_id})
            else:
                err_msg = res.stderr.strip() if res.stderr else "Non-zero exit code"
                notify_channel(effective_channel, f"GitHub sync failed: {err_msg}", "github_sync_failed", {"pr_id": pr_id, "error": err_msg})
        except Exception as e:
            notify_channel(effective_channel, f"GitHub sync failed: {str(e)}", "github_sync_failed", {"pr_id": pr_id, "error": str(e)})
```

#### Invocation to DELETE (from `orchestrator.py` line ~743):
```python
trigger_github_sync(workdir, effective_channel, base_filename)
```

#### Live LLM test assertion to REPLACE (in `e2e_test_triad_planner.sh`):
- **OLD (incorrect):**
```bash
PR_FILE=$(ls .sdlc_runs/*/dummy_triad_prd/PR_1_PL-999.md 2>/dev/null || true)
```
- **NEW (correct):** Replace with a glob that matches the actual planner output, e.g.:
```bash
PR_FILE=$(ls .sdlc_runs/*/dummy_triad_prd/PR_Slice_1.md 2>/dev/null || ls .sdlc_runs/*/dummy_triad_prd/PR_A.md 2>/dev/null || true)
```
*(Coder must verify the exact pattern against `spawn_planner.py` output directory structure before finalizing)*
