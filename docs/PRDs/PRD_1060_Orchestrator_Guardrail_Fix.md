# PRD 1060: Orchestrator Guardrail Fix & Anti-Reward Hacking Mechanism

## 1. Project & Context
- **Project:** leio-sdlc
- **Goal:** Fix Orchestrator Guardrail Issue (PRD 1060), avoid Git tracking for forensic data, and enforce strict test repair.

## 2. Background & Architectural Decision
The SDLC Orchestrator recently encountered an infinite loop and pipeline failure. The root cause is that `scripts/create_pr_contract.py` and `scripts/orchestrator.py` forcefully run `git add -f` to track the globally ignored `.sdlc_runs` folder. This pollutes the Git index and trips the Reviewer Guardrail.

We previously considered using `git add -f` during crashes, but this violates the principle of keeping ignored garbage out of Git. The NEW architect-approved mandate is: Keep `.sdlc_runs` entirely OUT of Git. Do not use git commits to preserve forensic crash data. Instead, just rename the directory on the local filesystem.

Removing this explicit `git add` behavior will cause older test cases (e.g., `tests/test_pr_002_immutability.py` and integration tests) to naturally fail in batches. The Coder must find all affected tests and legitimately fix them without reward hacking.

## 3. Requirements

### 3.1. Fix Git Tracking for `.sdlc_runs`
- **Scope:** `scripts/orchestrator.py`, `scripts/create_pr_contract.py`
- **Action:** Completely remove any explicit `git add` and `git commit` commands targeting `.sdlc_runs` or internal PR contract generation folders.
- **Context:** `.sdlc_runs/` is already in `.gitignore`. The scripts must respect this and stop trying to track forensic and contract artifacts.

### 3.2. State 5 Forensic Crash Preservation (File System over Git)
- **Scope:** `scripts/orchestrator.py`
- **Action:** Modify the fallback/crash handler (State 5 Escalate Tier 1 and `--cleanup` flows).
- **New Behavior:** Do NOT use `git add -f` or any git tracking for the directory. Instead, to preserve the forensic evidence, use Python's `os.rename` or `shutil.move` to rename the local directory from `.sdlc_runs/<PR_Name>` to `.sdlc_runs/<PR_Name>_crashed_<timestamp>`. Because it's ignored, `git clean -fd` will safely leave the renamed folder intact on the disk.

### 3.3. Test Repair (Strict Anti-Reward Hacking)
- **Scope:** `tests/test_pr_002_immutability.py`, `tests/test_orchestrator_handoff.py`, `tests/test_handoff_integration.py`, and any other tests affected.
- **Action:** The Coder MUST find ALL affected tests and properly fix them by updating mock expectations and adjusting assertions to align with the new git tracking behavior.
- **Constraint:** The Coder is STRICTLY FORBIDDEN from deleting test files or maliciously removing test assertions to artificially bypass failing checks. The tests must legitimately pass.

## 4. Technical Specifications
- **Files Modified:**
  - `scripts/orchestrator.py`: Remove `git add`/`git commit` for `.sdlc_runs`. Update State 5 error handling to rename local directory via `os.rename`/`shutil.move` instead of git commits.
  - `scripts/create_pr_contract.py`: Remove `git add` for `.sdlc_runs`.
  - `tests/test_pr_002_immutability.py`, `tests/test_orchestrator_handoff.py`, `tests/test_handoff_integration.py`, etc.: Update expectations and legitimately fix assertions.
- **Dependencies:** None.
- **Exclusions:** Strict exclusion of modifications to `playbooks/reviewer_playbook.md` or any Reviewer prompt/guardrail logic.

## 5. Success Metrics
- Orchestrator completes PR flow without Guardrail violations regarding `.sdlc_runs`.
- Crashed runs successfully rename the local folder to `*_crashed_*` without polluting git history.
- Test suite passes with full assertions intact (no removed/disabled tests).
