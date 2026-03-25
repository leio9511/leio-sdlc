# PR Contract: ISSUE-020 (Refactor CUJ-3: Spawn Reviewer)

## Overview
This PR refactors the 3rd Core User Journey (CUJ-3) by extending the "Limb Stubbing" architecture. We need to create a Python wrapper for spawning the Reviewer agent, update the `SKILL.md` instructions, and create an end-to-end mock test script.

## Acceptance Criteria (AC)

### 1. `scripts/spawn_reviewer.py`
You must create this Python script with the following exact logic and requirements:
- **Inputs**: Use `argparse` to accept `--pr-file <path>` and `--diff-target <target>` (e.g., `HEAD~1..HEAD` or `base_hash..latest_hash`).
- **Test Mode (`SDLC_TEST_MODE=true`)**: 
  - Do NOT call the OpenClaw API.
  - Append the exact string to `tests/tool_calls.log`: `{'tool': 'spawn_reviewer', 'args': {'pr_file': <path>, 'diff_target': <target>}}` (using Python dict to string conversion `str({...})` for single quotes).
  - Print `{"status": "mock_success", "role": "reviewer"}` to stdout.
  - Exit with code 0.
- **Production Mode**: 
  - Read the content of the `--pr-file`.
  - Construct a `task_string` that explicitly injects the PR Contract text AND instructs the Reviewer to "Execute git diff <diff_target>".
  - Use `subprocess.run(["openclaw", "sessions_spawn", task_string])` to spawn the sub-agent.
  - Handle file-not-found errors gracefully (exit 1).

### 2. Update the Skill Brain (`SKILL.md`)
You must modify `SKILL.md` precisely as follows:
- Locate Command Template 3 (Spawning the Reviewer) in `SKILL.md`.
- Replace the existing complex command/JSON with the following exact literal string:
  `To spawn a reviewer, use the \`exec\` tool to run: \`python scripts/spawn_reviewer.py --pr-file <path_to_pr> --diff-target <base_hash>..<latest_hash>\``

### 3. The Mock Test (`scripts/test_cuj_3_mock.sh`)
You must create this test script to verify the end-to-end flow:
- Create a test script that sets `export SDLC_TEST_MODE=true`.
- Runs the real OpenClaw agent: `openclaw agent -m "Coder 已经提交了代码 (Commit: abc1234)，基线是 master (Commit: def5678)，工单在 dummy_pr.md，请拉起 Reviewer 进行审查"`
- Asserts that `grep -q "'tool': 'spawn_reviewer'" tests/tool_calls.log` succeeds.