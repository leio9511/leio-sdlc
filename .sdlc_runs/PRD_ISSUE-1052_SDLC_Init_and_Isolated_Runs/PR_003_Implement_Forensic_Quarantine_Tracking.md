status: open

# PR-003: Implement Forensic Quarantine Tracking

## 1. Objective
Update the state escalation logic (State 5 Escalation / Tier 1 Reset) to ensure forensic logs within the globally git-ignored `.sdlc_runs/<PR_Name>` directory are forcefully tracked to the toxic branch.

## 2. Scope (Functional & Implementation Freedom)
Modify the error handling and cleanup mechanisms (e.g., within `orchestrator.py` during a `--cleanup` or State 5 Escalation) to explicitly execute `git add -f .sdlc_runs/<PR_Name>/`. This physically binds the forensic logs to the quarantine commit, preventing forensic data loss and state leakage across branches.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The `.sdlc_runs/` directory must be globally ignored (e.g., via `.git/info/exclude`) to allow safe execution of `git clean -fd`.
2. When a State 5 Escalation occurs, the system must forcefully add (`git add -f`) the isolated artifact directory to the quarantine commit.
3. The Coder MUST write tests to verify that `git clean -fd` cleans the workspace safely without deleting active runs, and that forensic data is successfully tracked during an escalation. All tests MUST run GREEN before submitting.