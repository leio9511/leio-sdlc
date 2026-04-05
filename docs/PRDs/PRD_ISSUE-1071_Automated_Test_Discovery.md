# PRD: Automated Test Discovery in Preflight

## 1. Context & Problem Definition
Currently, preflight.sh hardcodes the list of test scripts. If a developer adds a test but forgets to update preflight.sh, the test is bypassed in CI.

## 2. Requirements
- Refactor `preflight.sh` to use automated test discovery.
- Bash tests: Dynamically find and execute all `scripts/test_*.sh`.
- Python tests: Dynamically find and execute all `tests/test_*.py` using `python3 -m unittest discover` or similar.
- Maintain Token-Optimized CI (silent on success, verbose on failure).
- If any test fails, exit with a non-zero code.

## 3. Framework Modifications
- `preflight.sh` (modified)

## 4. Auditor Constraints (Red Team)
- **Empty Test Sets:** The script MUST handle cases where no bash tests or no python tests exist without failing (i.e., gracefully skip if `find` or glob returns empty).
- **Fail-Fast Implementation:** To preserve tokens and limit context pollution, the script should fail immediately upon the first test script failure, outputting only that specific failure log.
- **Redirection Safety:** Test execution output MUST be redirected to a temporary log file. Only output the log if the exit code is non-zero. Ensure temporary files are cleaned up properly (e.g., using `trap`).