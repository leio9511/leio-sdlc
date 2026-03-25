# PR Contract: ISSUE-020 (Refactor CUJ-4: Merge Code)

## Context & Objective
Refactor the 4th Core User Journey (CUJ-4) for the `leio-sdlc` project to improve testability. We need to replace the generic `bash` execution for merging code with a testable Python wrapper (`scripts/merge_code.py`) that supports a mockable boundary (`SDLC_TEST_MODE`).

## Task Details

### 1. Create `scripts/merge_code.py`
Create a Python script that strictly handles branch merge logic with the following requirements:
*   **Inputs:** Use `argparse` to accept `--branch <branch_name>`.
*   **Test Mode Interception:**
    *   Check for the environment variable `SDLC_TEST_MODE=true`.
    *   If `SDLC_TEST_MODE=true`, **DO NOT execute any `git` commands.**
    *   Append the exact string to `tests/tool_calls.log` using single quotes (e.g., via Python dict to string conversion `str({...})`):
        `{'tool': 'merge_code', 'args': {'branch': <branch_name>}}`
    *   Print exactly `{"status": "mock_success", "action": "merge"}` to `stdout`.
    *   Exit with code `0`.
*   **Production Mode:**
    *   If `SDLC_TEST_MODE` is not `true`, execute the actual `git merge` command securely using `subprocess.run`.
    *   Command to execute: `subprocess.run(['git', 'merge', <branch_name>])` (or similar secure list-based invocation).
    *   Handle potential merge conflicts gracefully: if `git merge` fails, print the error and exit with a non-zero code.

### 2. Update `SKILL.md`
Locate Command Template 4 (Merge and Deploy) in `SKILL.md`.
You must completely replace the existing `bash` command with the following exact literal string:
`To merge approved code, use the \`exec\` tool to run: \`python scripts/merge_code.py --branch <branch_name>\``

### 3. Create Mock Test `scripts/test_cuj_4_mock.sh`
Create a bash test script for End-to-End mock validation:
*   Set `export SDLC_TEST_MODE=true`.
*   Run the real OpenClaw agent with the command: `openclaw agent -m "Reviewer 已经给了 LGTM，请把 feature/login 分支合并到 master"`
*   Assert the mock log using: `grep -q "'tool': 'merge_code'" tests/tool_calls.log`.
*   Ensure the script fails if the `grep` assertion fails.

## Acceptance Criteria (AC)
1. `scripts/merge_code.py` is created, uses `argparse` for `--branch`, and strictly implements `SDLC_TEST_MODE` interception.
2. Under `SDLC_TEST_MODE=true`, the script appends exactly `{'tool': 'merge_code', 'args': {'branch': <branch_name>}}` to `tests/tool_calls.log` (with single quotes) and prints `{"status": "mock_success", "action": "merge"}` to `stdout`, exiting with `0`. No git commands are executed.
3. Under production mode, the script executes the actual git merge securely using `subprocess.run` (e.g., `subprocess.run(['git', 'merge', branch_name])`) and handles failures by printing the error and exiting non-zero.
4. `SKILL.md` Command Template 4 is updated. The previous bash command is completely replaced with the exact string: `To merge approved code, use the \`exec\` tool to run: \`python scripts/merge_code.py --branch <branch_name>\``.
5. `scripts/test_cuj_4_mock.sh` is created, exports `SDLC_TEST_MODE=true`, runs the native agent (`openclaw agent -m "Reviewer 已经给了 LGTM，请把 feature/login 分支合并到 master"`), and asserts success via `grep -q "'tool': 'merge_code'" tests/tool_calls.log`.