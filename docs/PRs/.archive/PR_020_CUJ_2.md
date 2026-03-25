# PR Contract: ISSUE-020 (Refactor CUJ-2: Spawn Coder)

## Context & Objectives
This PR applies the "Limb Stubbing via Dependency Injection" architecture to CUJ-2 (Spawn Coder), replacing brittle JSON payload generation with a testable Python wrapper. The wrapper must support dual file-path inputs for Direct Context Injection and intercept execution during test modes to enable zero-side-effect automated testing for the Manager.

## Acceptance Criteria (AC)

**IMPORTANT: Do not reference external PRDs for these details. Implement them exactly as specified below.**

### 1. Create `scripts/spawn_coder.py`
You must write a Python script at `scripts/spawn_coder.py` that implements the following requirements exactly:

- **CLI Parsing:** Use `argparse` to accept exactly two arguments: `--pr-file <path>` and `--prd-file <path>`.
- **Test Mode Interception:** 
  If the environment variable `SDLC_TEST_MODE=true` is present:
  - You MUST NOT call the OpenClaw API.
  - You MUST append the following exact Python string format to `tests/tool_calls.log` using `str({...})` to ensure single quotes:
    `{'tool': 'spawn_coder', 'args': {'pr_file': <path>, 'prd_file': <path>}}`
    *(Note: Replace `<path>` with the actual parsed variable values).*
  - You MUST print exactly `{"status": "mock_success", "role": "coder"}` to `stdout`.
  - You MUST exit with code 0.
- **Production Mode (Default):**
  If `SDLC_TEST_MODE` is not `true`:
  - You MUST read the contents of BOTH the PR file and the PRD file.
  - You MUST construct a `task_string` that explicitly injects both the PR Contract text and the PRD text to ensure the Coder has full context.
  - You MUST execute the spawn command using exactly: `subprocess.run(["openclaw", "sessions_spawn", task_string])`.
  - You MUST handle file-not-found errors gracefully by exiting with code 1.

### 2. Update `SKILL.md` (Command Template 2)
You must modify `SKILL.md` to update the instructions for spawning the coder.

- Locate "Command Template 2" (Spawning the Coder).
- Delete the existing complex command or JSON payload instructions.
- Completely replace it with the following EXACT literal string:
  `To spawn a coder, use the \`exec\` tool to run: \`python scripts/spawn_coder.py --pr-file <path_to_pr> --prd-file <path_to_prd>\``

### 3. Create E2E Mock Validation Test `scripts/test_cuj_2_mock.sh`
You must write a Bash test script at `scripts/test_cuj_2_mock.sh` that implements an end-to-end mock test:

- Set `export SDLC_TEST_MODE=true` in the script.
- Execute the real OpenClaw agent using exactly this command:
  `openclaw agent -m "PR合约已就绪在 dummy_pr.md，技术字典在 dummy_prd.md，请安排 Coder 开始开发"`
- After the agent finishes, assert that the log was written properly by running exactly:
  `grep -q "'tool': 'spawn_coder'" tests/tool_calls.log`
  *(The script should fail if this grep fails).*
- The test script must execute successfully from start to finish in less than 10 seconds.
