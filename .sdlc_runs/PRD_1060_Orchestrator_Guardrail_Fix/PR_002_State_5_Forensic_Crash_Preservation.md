status: in_progress

# PR-002: State 5 Forensic Crash Preservation

## 1. Objective
Preserve forensic data during crashes safely by copying the state directory instead of moving it, maintaining the original directory for retry loops.

## 2. Scope (Functional & Implementation Freedom)
- When a crash occurs in the State 5 error handling block (Tier 1 retry loop), use `shutil.copytree` (with `dirs_exist_ok=True`) to create a snapshot of the run directory.
- NEVER use `os.rename` or `shutil.move` in this Tier 1 retry loop block to ensure the original directory remains intact for subsequent steps.
- EXPLICIT MANDATE: The `os.rename` behavior used inside the quarantine/cleanup block MUST be fully preserved and completely unaffected by this change.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. Crashed runs successfully copy the local folder for forensic analysis without deleting the original and without polluting git history.
2. The quarantine feature (cleanup block) correctly uses `os.rename` and continues to function as expected.
3. The Coder MUST ensure all tests run GREEN before submitting.