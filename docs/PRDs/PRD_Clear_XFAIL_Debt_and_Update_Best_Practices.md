---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Clear_XFAIL_Debt_and_Update_Best_Practices

## 1. Context & Problem (业务背景与核心痛点)
We have successfully migrated `leio-sdlc` to use `pytest`, but discovered 20 test failures across 11 files that were previously hidden. A previous attempt to fix all of them in one PR failed due to "Context Collapse" and orchestrator instability (ISSUE-1145). We need to clear this technical debt systematically and document the manual mitigation strategy for "Massive Test Failures" in the project's README to prevent future recurrences.

## 2. Requirements & User Stories (需求定义)
- **User Story 1:** As a developer, I want all `@pytest.mark.xfail` markers removed and the underlying test logic fixed so that the codebase has 100% genuine green tests.
- **User Story 2:** As an Architect, I want the project's `README.md` updated with the "Manual Blast Radius Control" protocol to guide future large-scale refactorings.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
> **[CRITICAL INSTRUCTION FOR PLANNER]**
> You MUST slice this PRD into multiple PRs (Micro-Slicing). 
> **Constraint:** Each PR MUST NOT attempt to fix more than **2 test files** at a time.
> **Target Files (The Debt List):**
> 1. `tests/test_reaper_logic.py`
> 2. `tests/test_pr_003_1_debug_cli.py`
> 3. `tests/test_path_decoupling.py`
> 4. `tests/test_pr_004_rollback.py`
> 5. `tests/test_orchestrator_resilience.py`
> 6. `tests/test_singleton_lock.py`
> 7. `tests/test_spawn_auditor.py`
> 8. `tests/test_orchestrator_handoff.py`
> 9. `tests/test_spawn_reviewer_history.py`
> 10. `tests/test_orchestrator_cli.py`
> 11. `tests/test_orchestrator_doctor.py`
> 12. `README.md` (Documentation update)

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Debt Clearance**
  - **Given** the 11 files listed in Section 3 contain `xfail` markers.
  - **When** the SDLC pipeline completes.
  - **Then** `grep -r "pytest.mark.xfail" tests/` must return zero results.
  - **And** `./preflight.sh` must be 100% green.

- **Scenario 2: README Update**
  - **Given** the `README.md` file.
  - **When** the documentation PR is merged.
  - **Then** the file contains the "Manual Blast Radius Control" protocol as defined in Section 7.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Phased TDD:** Remove markers -> Run failed tests -> Analyze logs -> Fix logic/mocks -> Verify Green -> Merge.
- **Isolation:** Each PR slice handles only 1-2 files to keep the Coder agent focused and prevent log overflow.

## 6. Framework Modifications (框架防篡改声明)
- `README.md`: Authorized for documentation update.
- All files in `tests/`: Authorized for logic fixes.

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Manual phased cleanup strategy after automatic "Big Bang" failure.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**

- **`README_Protocol_Update` (Append to a new "Best Practices" section or "Known Limitations" in README.md)**:
```markdown
### ⚠️ Manual Blast Radius Control (Emergency Protocol)
Current SDLC versions cannot automatically handle massive test failures (context collapse). 
Until ISSUE-1141 is implemented, if a PRD is expected to break many tests:
1. Manually identify all affected files.
2. Explicitly list each file in the PRD.
3. Force the Planner to limit each PR slice to a maximum of 2 files.
```