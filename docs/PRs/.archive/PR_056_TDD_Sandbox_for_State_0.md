status: open

# PR Contract: PRD-054-02 - TDD Sandbox for State 0
title: PRD-054-02 - TDD Sandbox for State 0
status: open
slice_depth: 0

## 1. Goal
Update `scripts/test_orchestrator_fsm.sh` to include deterministic sandbox scenarios for State 0.

## 2. Requirements
Implement the following scenarios in the test script:
1. **Pure State 0 Start**: Provide new `--prd-file`, stub planner returns 1 PR, assert transition to State 2.
2. **Idempotency (Resume)**: Provide `--prd-file` with existing `open` PR, assert planner is NOT called.
3. **Elastic Slicing (Single PR)**: Stub planner returns exactly 1 PR, assert no error.
4. **Planner Failure (Zero PRs)**: Stub planner returns 0 files, assert exit code 1 and "Fatal" message.
5. **Transition Integrity**: Verify full lifecycle (Coder/Reviewer) still works after State 0.

## 3. Files to Modify
- `scripts/test_orchestrator_fsm.sh`

## 4. Verification
- Execute `bash scripts/test_orchestrator_fsm.sh` and verify all State 0 scenarios pass.
