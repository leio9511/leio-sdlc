status: open

# PR-2: Forensic Quarantine Tracking

## 1. Objective
Update the orchestrator to forcefully track the ignored `.sdlc_runs/<PR_Name>/` directory into the "WIP: FORENSIC CRASH STATE" quarantine commit during a State 5 Escalation.

## 2. Scope (Functional & Implementation Freedom)
- Modify the orchestrator's State 5 Escalation logic (`--cleanup` or Tier 1 Reset).
- The orchestrator MUST execute `git add -f .sdlc_runs/<PR_Name>/` to forcefully track the ignored directory.
- This ensures that forensic logs are physically bound to the toxic branch.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- During a State 5 Escalation, the `.sdlc_runs/<PR_Name>/` directory is successfully added to the git index.
- The generated "WIP: FORENSIC CRASH STATE" commit contains the contents of the `.sdlc_runs/<PR_Name>/` directory.
- The Coder MUST write or update tests for this specific functional slice. All tests MUST pass (GREEN) before submitting.
