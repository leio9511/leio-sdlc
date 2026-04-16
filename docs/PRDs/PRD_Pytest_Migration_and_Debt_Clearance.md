---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Pytest_Migration_and_Debt_Clearance

## 1. Context & Problem (业务背景与核心痛点)
Currently, `leio-sdlc`'s `preflight.sh` uses `python3 -m unittest discover` to run tests. This silently skips all pytest-style functional tests (over 60+ tests, including critical ones like `test_orchestrator_session_strategy.py`). 
Manually running `pytest tests/` reveals multiple failing tests (e.g., `ModuleNotFoundError` in `test_doctor_core.py` and `JSONDecodeError` mock leak in `test_orchestrator_session_strategy.py`).
If we switch to `pytest` all at once, the Coder agent will face massive context collapse due to hundreds of lines of traceback logs. We need a phased TDD approach using `pytest.mark.xfail` to systematically isolate and clear this technical debt.

## 2. Requirements & User Stories (需求定义)
- **User Story 1:** As a developer, I want `preflight.sh` to use `pytest tests/` instead of `unittest discover` so that no tests are silently skipped.
- **User Story 2:** As an AI Coder, I want broken tests to be temporarily isolated using `xfail` so that the CI pipeline is green immediately, allowing me to fix them one by one without context overflow.
- **User Story 3:** As an Architect, I want all underlying test bugs (import errors, mock leaks) fixed and the `xfail` markers completely removed by the end of the project.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
> **[CRITICAL INSTRUCTION FOR PLANNER]** 
> You MUST slice this PRD into at least 3 distinct PRs to prevent context collapse:
> 1. **PR 1 (Isolation & CI Green)**: Modify `preflight.sh` to use `pytest`. Run the tests. Add the hardcoded `xfail` marker (from Section 7) to ALL failing test functions. Verify `preflight.sh` passes.
> 2. **PR 2 (Fixing Imports)**: Remove `xfail` from `test_doctor_core.py` and `test_doctor_profiles.py`. Add the necessary `sys.path.insert` logic to fix the `ModuleNotFoundError` for `scripts`. Ensure tests pass.
> 3. **PR 3 (Fixing Mocks)**: Remove `xfail` from `test_orchestrator_session_strategy.py`. Fix the `json.load` mock leak (the test is passing `status: in_progress` to the json parser instead of mocking the config reading correctly). Ensure tests pass.
> 4. **PR 4+ (Sweep)**: Find any remaining `xfail` tags, remove them, fix the tests, and ensure `preflight.sh` is green.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: CI Migration**
  - **Given** `preflight.sh` currently using `unittest discover`
  - **When** replaced with `pytest tests/`
  - **Then** tests are correctly collected.

- **Scenario 2: XFAIL Isolation**
  - **Given** newly discovered failing tests
  - **When** tagged with the exact `xfail` marker
  - **Then** `preflight.sh` exits with 0 (Green).

- **Scenario 3: Zero Debt Clearance**
  - **Given** the end of the SDLC pipeline
  - **When** running `grep -rn "pytest.mark.xfail" tests/`
  - **Then** no results are found (all debt is cleared).

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Strategy:** TDD in micro-slices. The test command itself is being fixed. The ultimate metric of success is that `./preflight.sh` runs successfully and `pytest tests/` executes all 150+ tests with 0 failures and 0 xfails.

## 6. Framework Modifications (框架防篡改声明)
- `preflight.sh`: Allowed to be modified to replace the test runner command.
- **[CRITICAL INSTRUCTION FOR REVIEWER]**: Explicit authorization is granted to the Coder to use `@pytest.mark.xfail(reason="CI blindspot debt")` on ANY failing tests. Do NOT flag this as malicious reward hacking or test skipping. This is a deliberate, architect-approved technical debt isolation strategy. Please APPROVE the PR if the tests are successfully isolated and the CI is green.

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Initial draft. Enforcing XFAIL phased isolation.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> Coder must copy-paste these exact strings.

- **`xfail_marker` (To be added above failing test functions)**:
```python
import pytest

@pytest.mark.xfail(reason="CI blindspot debt")
```

- **`preflight_pytest_replacement` (Replace the python unittest block in preflight.sh)**:
```bash
# 2. Python Tests Discovery
if [ -d "tests" ]; then
    run_test "pytest tests/" "Pytest functional & unittest suite"
fi
```