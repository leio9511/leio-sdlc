status: in_progress

# PR-1: Core Artifact Isolation

## 1. Objective
Modify the core scripts to ensure all runtime artifacts are written to and read from a specific `.sdlc_runs/<PR_Name>/` directory instead of the project root.

## 2. Scope (Functional & Implementation Freedom)
- Modify the orchestrator, coder, reviewer, and merge scripts to handle the new runtime artifact directory structure.
- The scripts should dynamically determine the correct `.sdlc_runs/<PR_Name>/` path.
- The artifacts to be relocated include, but are not limited to: `Review_Report.md`, `current_review.diff`, `recent_history.diff`, `current_arbitration.diff`, `.coder_session`, and `build_preflight.log`.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- No runtime artifacts are generated in the project root.
- All scripts correctly read and write artifacts to the appropriate `.sdlc_runs/<PR_Name>/` directory.
- The Coder MUST write or update tests for this specific functional slice. All tests MUST pass (GREEN) before submitting.
