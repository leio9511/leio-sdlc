# PR_017: Implement Skill Test Runner Protocol

## 1. Description
This PR addresses the implementation of the `skill_test_runner` as defined in Section 3.4 of `PRD_010_SDLC_Self_Evolution.md`. Due to previous process violations, this document serves as the formal, regenerated contract for the implementation of the agentic integration testing gate.

The `skill_test_runner` will act as a universal testing probe to spawn sub-agents, mount target skills, and verify their logic before deployment.

## 2. Requirements & Design Specifications
According to **PRD_010 Section 3.4 (Skill Test Runner Protocol)**, the implementation MUST adhere to the following interface and behavior:

- **Inputs**:
  1. `SKILL_PATH`: Absolute or relative path to the target skill directory.
  2. `TEST_PROMPT` (Optional): Natural language instruction to trigger the skill. Default: "READY?".
- **Execution Workflow**: 
  - Spawns a sub-agent.
  - Mounts the target skill (using the provided `SKILL_PATH`).
  - Evaluates the sub-agent's response, expecting the specific string `"TEST_PASSED"`.
- **Outputs**:
  - **Stdout**: Real-time logs of the sub-agent's reasoning and tool calls.
  - **Exit Code**: `0` for verified success, `1` for any failure or timeout.

## 3. Tasks for Coder
- [ ] Create or update the core script for the test runner (e.g., `scripts/skill_test_runner.sh` or `scripts/agentic_smoke_test.sh`).
- [ ] Implement argument parsing for `SKILL_PATH` and `TEST_PROMPT`.
- [ ] Implement the sub-agent spawning mechanism, ensuring the target skill is correctly mounted.
- [ ] Parse the sub-agent output for the `"TEST_PASSED"` string to determine the final exit code.
- [ ] Ensure stdout streams the sub-agent's reasoning and tool calls while executing.
- [ ] Integrate the test runner into the pre-deployment gates (`preflight.sh` / `deploy.sh`).

## 4. Acceptance Criteria (AC)
- [ ] The `skill_test_runner` correctly accepts `SKILL_PATH` and `TEST_PROMPT` as inputs.
- [ ] The script successfully spawns a sub-agent, mounts the specified skill, and streams logs to stdout.
- [ ] The script correctly returns exit code `0` when the sub-agent outputs `"TEST_PASSED"`, and `1` otherwise.
- [ ] **Crucial**: The `skill_test_runner` is successfully validated in a real-world scenario using the `skill_util/kanban` skill. A specific test using this kanban skill must run and pass.
- [ ] The test runner successfully blocks the pipeline if a sub-agent test fails.
