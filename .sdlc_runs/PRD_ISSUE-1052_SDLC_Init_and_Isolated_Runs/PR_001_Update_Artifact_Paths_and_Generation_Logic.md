status: in_progress

# PR-001: Update Artifact Paths and Generation Logic

## 1. Objective
Update core orchestration and spawn scripts to generate, read, and write all runtime artifacts (e.g., Review_Report.md, .coder_session, diffs) within a dedicated, isolated directory (`.sdlc_runs/<PR_Name>/`) instead of the project root.

## 2. Scope (Functional & Implementation Freedom)
Modify the logic responsible for creating and accessing runtime artifacts and session states so that they use the new isolated `.sdlc_runs/` structure. This ensures the project root remains clean and unaffected by runtime output.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. Artifact generation functions must correctly route all outputs to the `.sdlc_runs/<PR_Name>/` directory.
2. The system must create the directory if it does not exist.
3. The Coder MUST write or update tests to verify that no artifacts are created in the project root and that they are correctly placed in the isolated directory. All tests MUST run GREEN before submitting.