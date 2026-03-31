status: open

# PR-1: Protect Runtime Artifacts from git clean

## 1. Objective
Modify the orchestrator's sandbox initialization to prevent `git clean -fd` from deleting critical runtime artifacts by dynamically adding them to `.git/info/exclude`.

## 2. Scope (Functional & Implementation Freedom)
- The Coder is to enhance the sandbox initialization logic within the orchestrator script.
- This enhancement involves appending a predefined list of critical SDLC runtime artifacts to the `.git/info/exclude` file, ensuring they persist through workspace cleaning operations.
- The implementation must be idempotent, meaning it must check if an artifact is already listed in `.git/info/exclude` before appending it, to avoid duplicate entries.
- The existing log message related to sandbox initialization must be updated to accurately reflect that multiple runtime artifacts are now being protected.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- After the orchestrator initializes, the following artifacts must be present in the `.git/info/exclude` file:
  - `Review_Report.md`
  - `current_review.diff`
  - `recent_history.diff`
  - `current_arbitration.diff`
  - `.coder_session`
  - `.coder_state.json`
  - `build_preflight.log`
  - `.tmp/`
- The script must not create duplicate entries for artifacts that already exist in the exclude file.
- The orchestrator's startup message must be updated to indicate that SDLC runtime artifacts are being added to the exclude file.
- The Coder is responsible for writing necessary tests to validate this functionality, and all existing and new tests MUST pass (GREEN) before submission.
