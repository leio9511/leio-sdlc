# PRD: E2E Testing Architecture Refactoring (Staggered Migration)
**Issue ID:** ISSUE-1119
**Project:** leio-sdlc

## 1. Context & Problem
The `leio-sdlc` E2E test suite has grown organically and contains 20+ valid tests along with several deprecated ones. A previous attempt to refactor the entire suite in a single PR failed due to context overflow and quota limits. 
Additionally, the suite suffers from:
1. "Shotgun Surgery" patterns where each test script manually copies dependencies into its sandbox.
2. Lack of distinction between deterministic (mocked) and non-deterministic (Live LLM) tests.
3. Frequent failures due to missing `utils_json.py` in sandboxed environments.

## 2. Requirements & User Stories
- **Requirement 1 (Infrastructure & Seed):** Create `scripts/e2e/mocked/` and `scripts/e2e/live_llm/`. Create a centralized fixture `scripts/e2e/setup_sandbox.sh`. Move a single "seed" test (`e2e_test_orchestrator_fsm.sh`) to `mocked/` and refactor it to use the fixture.
- **Requirement 2 (Staggered Batch Migration):** Move the remaining 20+ valid E2E tests into the correct subdirectories in small, manageable batches (max 5 tests per PR).
- **Requirement 3 (Sandbox Dependency Injection):** Ensure `setup_sandbox.sh` copies `orchestrator.py`, `utils_json.py`, and all related scripts into the test environment. Fix all `ModuleNotFoundError` issues.
- **Requirement 4 (Preflight Guardrail Upgrade):** Update `preflight.sh` to:
    - Default behavior: Run all tests in `mocked/`.
    - Exit behavior: Any failure in `mocked/` MUST result in `exit 1` (blocking build).
    - Optional flag: `--live-llm` to run tests in `live_llm/` (non-blocking, warning only).

## 3. Architecture & Technical Strategy
- **Centralized Sandbox Fixture:** Create `scripts/e2e/setup_sandbox.sh`. This script must export a function `init_hermetic_sandbox`.
    - **Path Stability:** The script MUST use `PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"` to anchor itself to the project root, ensuring file copies work regardless of the CWD.
    - **Dependency Injection:** The function must copy `orchestrator.py`, `utils_json.py`, and other required scripts into the provided target directory.
- **Planner Micro-Slicing Mandate:** The Planner MUST break this PRD into multiple dependency-ordered PRs. 
    - PR 1: Infrastructure (folders + `setup_sandbox.sh`) and 1st Seed test (`e2e_test_orchestrator_fsm.sh`).
    - PR 2-N: Batch file moves (max 5 files each) and refactoring to use the fixture.
    - Final PR: `preflight.sh` logic overhaul.
- **Strict I/O Policy:** Coder MUST use native `write/edit` APIs for file modifications. **STRICTLY PROHIBITED:** Using `cat << EOF` or `sed/awk` to manipulate code.
- **TDD Exit Conditions:** Every PR in the chain must have a clear acceptance test: the specific tests moved or the infrastructure created must be verified green before merging.

## 4. Acceptance Criteria
- [ ] `scripts/e2e/` is organized into `mocked/` and `live_llm/`.
- [ ] `setup_sandbox.sh` is the single source of truth for sandbox initialization.
- [ ] `bash preflight.sh` runs all mocked tests by default and exits 1 on any failure.
- [ ] No `ModuleNotFoundError: No module named 'utils_json'` occurs in any retained test.
- [ ] Total migration of all 20+ valid tests is completed without context overflow.

## 5. Overall Test Strategy
- Individual PR validation: Run each migrated batch manually.
- Final validation: `bash preflight.sh` must be 100% green.

## 6. Framework Modifications
No core logic changes to the SDLC engine; purely a test infrastructure refactoring.

## 7. Hardcoded Content
- **Directory names:** `mocked/`, `live_llm/`
- **Warning string:** `[E2E WARNING]`
- **Bash Function Skeleton:**
```bash
init_hermetic_sandbox() {
    local target_dir="$1"
    if [ -z "$target_dir" ]; then
        echo "Error: target_dir is required"
        return 1
    fi
    # Implementation: find PROJECT_ROOT via BASH_SOURCE, then cp dependencies
}
```
- **Path Resolution Pattern:**
```bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
```

