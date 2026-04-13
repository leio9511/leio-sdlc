# PRD: E2E Testing Architecture Refactoring & Sandbox Fixes
**Issue ID:** ISSUE-1119
**Project:** leio-sdlc

## 1. Context & Problem
Currently, the `preflight.sh` script runs all E2E tests inside `scripts/e2e/` blindly. This includes:
1. 8 deprecated tests (e.g., natural language CUJs, outdated blue-green, kanban).
2. Pure logic tests (mocked) and live LLM tests mixed together.
Furthermore, the recent extraction of `utils_json.py` broke several core E2E tests (e.g., `e2e_test_orchestrator_fsm.sh`, `e2e_test_hierarchical_resilience.sh`) because the test sandbox creation scripts were not updated to copy `utils_json.py` into the temporary execution directories.

## 2. Requirements & User Stories
- **Requirement 1:** Delete the 8 deprecated E2E tests (`e2e_test_kanban_runner.sh`, `e2e_test_blue_green_deploy.sh`, `e2e_test_cuj_1_mock.sh` through `e2e_test_cuj_5_mock.sh`, and `e2e_test_yellow_path.sh`).
- **Requirement 2:** Refactor the `scripts/e2e/` directory by creating two subdirectories: `mocked/` and `live_llm/`. Move `e2e_test_triad_planner.sh` and `e2e_test_triad_reviewer.sh` to `live_llm/`. Move all remaining valid E2E tests into `mocked/`.
- **Requirement 3:** Fix the `ModuleNotFoundError: No module named 'utils_json'` using a Centralized Fixture pattern. Create a common `setup_sandbox.sh` script or function that encapsulates the logic for preparing the E2E execution environment (copying `orchestrator.py`, `utils_json.py`, and other required dependencies). Update all E2E tests to source or call this centralized fixture instead of copying files individually.
- **Requirement 4:** Modify `preflight.sh` to remove the `--e2e-test` flag logic. The default execution of `preflight.sh` MUST automatically run all tests in `scripts/e2e/mocked/`. Add a new optional flag `--live-llm` which, if provided, will run the tests in `scripts/e2e/live_llm/`.
- **Requirement 5:** Change the failure behavior in `preflight.sh`. Mocked E2E tests are deterministic; therefore, if any test in `scripts/e2e/mocked/` fails, `preflight.sh` MUST exit with status 1 (blocking the build). Live LLM tests (`scripts/e2e/live_llm/`) are flaky by nature; if they fail, the script should output an `[E2E WARNING]` but continue execution without exiting with an error code.

## 3. Architecture & Technical Strategy
- **File Deletions:** Git rm the 8 deprecated scripts.
- **Directory Structure:** Create `scripts/e2e/mocked` and `scripts/e2e/live_llm`. Git mv the scripts accordingly.
- **Centralized Sandbox Fixture:** Create `scripts/e2e/setup_sandbox.sh` which exports a function (e.g., `init_hermetic_sandbox()`). This function must dynamically find the project root and copy all `.py` files from `scripts/` (including `utils_json.py`) and required config files into a provided temp directory. Modify the individual E2E test scripts to `source scripts/e2e/setup_sandbox.sh` and invoke the initialization function. (Use Python/Native APIs to refactor the bash scripts, absolutely NO sed/awk shotgun surgery).
- **Preflight Modification:** Update `preflight.sh` to change the loop from `scripts/e2e/*.sh` to `scripts/e2e/mocked/*.sh` (default) and conditionally `scripts/e2e/live_llm/*.sh` based on argument parsing. Adjust the failure response `exit 1` vs `[E2E WARNING]` logic.

## 4. Acceptance Criteria
- [ ] 8 deprecated files are removed from the repository.
- [ ] `scripts/e2e/` contains `mocked/` and `live_llm/` folders.
- [ ] `live_llm/` contains exactly 2 triad scripts.
- [ ] Running `bash preflight.sh` successfully executes all mock E2E tests and exits with 0.
- [ ] Running `bash preflight.sh` does NOT run the live LLM triad tests.
- [ ] Running `bash preflight.sh --live-llm` runs the live LLM tests, treating failures only as warnings.
- [ ] If ANY mock E2E test in `scripts/e2e/mocked/` fails, `preflight.sh` MUST exit with code 1 immediately.

## 5. Overall Test Strategy
- Unit test: N/A
- Integration/E2E test: Run `preflight.sh` locally to verify 0 failures and correct routing of mocked vs live tests.

## 6. Framework Modifications
No core framework changes. This is pure test infrastructure refactoring.

## 7. Hardcoded Content
- Directory names: `mocked/`, `live_llm/`
- Command flag: `--live-llm`
- Error message to fix: `ModuleNotFoundError: No module named 'utils_json'`
- Log message on live_llm test failure: `[E2E WARNING]`
- Centralized fixture script: `scripts/e2e/setup_sandbox.sh`
- Fixture function name: `init_hermetic_sandbox()`