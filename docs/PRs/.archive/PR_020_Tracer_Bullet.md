# PR_020: Tracer Bullet (CUJ-1 Refactor)

## 1. Context & Goals
This is a self-contained work order for the Coder to implement the "Tracer Bullet" phase of ISSUE-020. The goal is to refactor the architecture of the `leio-sdlc` skill to support Limb Stubbing via Dependency Injection, specifically focusing on CUJ-1 (Spawning the Planner).

By shifting from a generic tool to a custom local Python wrapper, we aim to achieve 100% deterministic, zero-side-effect testing, preventing hallucination risks and untestability caused by massive JSON payloads in `sessions_spawn`.

## 2. Implementation Tasks

### Task 1: Create `scripts/spawn_planner.py`
You must write a Python wrapper script that replaces the direct CLI invocation of `sessions_spawn`.
**Strict Logic Requirements:**
- **Language**: Must be written in Python to avoid Bash quoting/escaping hell (the ghost of ISSUE-001).
- **Interface**: Instead of taking a massive system prompt string from the CLI, it should take simple arguments: `--prd-file <path>`.
- **Logic (Production Mode)**: The Python script will read the PRD file, assemble the complex `task` prompt string internally, and invoke the OpenClaw API (or CLI) to spawn the sub-agent.
- **Logic (Test Mode)**: If the environment variable `SDLC_TEST_MODE=true` is present, the script MUST NOT call OpenClaw. Instead, it must:
  1. Append the intercepted arguments to a log file (e.g., `tests/tool_calls.log`).
  2. Print a mock success message (e.g., `{"status": "mock_success", "role": "planner"}`).
  3. Exit with code `0`.

### Task 2: Update the Skill Brain (`SKILL.md`)
You must modify `SKILL.md` to use the new Python script:
- Modify "Command Template 1".
- Remove the massive `sessions_spawn` JSON template completely.
- Instruct the Manager: "To spawn a planner, use the `exec` tool to run: `python scripts/spawn_planner.py --prd-file <path_to_prd>`".

### Task 3: Create the Mock Test (`scripts/test_cuj_1_mock.sh`)
You must write a shell script to verify the test mode:
- Create a dedicated test script `scripts/test_cuj_1_mock.sh`.
- It must set `export SDLC_TEST_MODE=true`.
- It must invoke the global test runner against the modified skill with a CUJ-1 trigger prompt.
- It must assert that the runner completes and that `tests/tool_calls.log` contains the expected mock invocation.

## 3. Acceptance Criteria (AC)
The following AC must be met exactly as specified (extracted directly from the PRD):
- [ ] `scripts/spawn_planner.py` exists and handles both Production and Test modes.
- [ ] `SKILL.md` is updated to use the new Python script for CUJ-1.
- [ ] `scripts/test_cuj_1_mock.sh` runs successfully in less than 5 seconds (proving it didn't actually spawn a heavy sub-agent).
- [ ] The Python script uses file paths (`--prd-file`) rather than raw text arguments to prevent escaping bugs.

## 4. Anti-Patterns (Do NOT do these)
- **Do not rewrite all 5 CUJs yet**. Focus only on CUJ-1. If the architecture is flawed, we want to fail fast on one component.
- **No Bash Wrappers for Spawn**: Do not use Bash for the `spawn_planner` script. Python only.
