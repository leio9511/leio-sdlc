---
title: "Fix Orchestrator Resilience Test Regressions"
id: "PRD_Fix_Orchestrator_Resilience_Test_Regressions"
status: "open"
# The 'Affected_Projects' is a mandatory list of project names that this PRD will touch.
# Example: Affected_Projects: [leio-sdlc, AMS]
Affected_Projects: [leio-sdlc]
---

### 1. Problem Statement
The test suite for `leio-sdlc`, specifically `tests/test_orchestrator_resilience.py`, is failing due to recent refactoring of the main `orchestrator.py` script. Key functions that were previously mocked in the tests (e.g., `initialize_sandbox`) have been removed or changed, causing `AttributeError` exceptions during test runs. Additionally, the "Yellow Path" test logic is flawed, causing it to incorrectly escalate to a "Red Path" (hard reset) and fail its assertions.

### 2. Solution
The solution is to update the test file `tests/test_orchestrator_resilience.py` to align with the current state of `orchestrator.py`. This involves:
- Removing mock patches for functions that no longer exist.
- Adjusting the test logic and assertions to correctly simulate and verify the intended "Yellow Path" behavior without triggering a premature escalation.

This change is limited to the test suite and does not affect production code, but it is critical for maintaining CI/CD integrity.

### 3. Architecture
- **Component:** `leio-sdlc` Test Suite
- **File to be modified:** `/root/.openclaw/workspace/projects/leio-sdlc/tests/test_orchestrator_resilience.py`
- **Architectural Impact:** None. This is a maintenance task to ensure the test harness is up-to-date.

### 4. BDD Acceptance Criteria

**Scenario: A developer runs the orchestrator resilience test suite.**
- **Given:** A clean checkout of the `leio-sdlc` repository.
- **When:** The developer executes `pytest tests/test_orchestrator_resilience.py`.
- **Then:** The test suite should complete successfully with all tests passing, confirming that the mocks align with the orchestrator's current implementation and that the Yellow/Red path logic is correctly tested.

### 5. Test Strategy
- The primary validation is running the `pytest` command on the specified test file and ensuring it passes.
- No new production code is being introduced, so the existing E2E tests for the SDLC pipeline itself are sufficient. The fix *is* the test.

### 6. Framework Modifications
The following file within the SDLC framework will be modified:
- `tests/test_orchestrator_resilience.py`
