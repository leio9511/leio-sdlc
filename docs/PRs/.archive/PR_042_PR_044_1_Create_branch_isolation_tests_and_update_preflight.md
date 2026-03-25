status: open

---
status: open
dependencies: []
---
# PR_044_1: Create branch isolation tests and update preflight

## Objective
Create the testing infrastructure for the branch isolation guardrail (TDD).

## Tasks
1. Create `scripts/test_branch_isolation.sh`.
2. Implement Scenario 1: Rejection on Master. Ensure the workspace is on `master`, run `spawn_coder.py --workdir $(pwd) --pr-file dummy.md --prd-file dummy.md`, and assert exit code `1` with the exact `[ACTION REQUIRED]` string.
3. Implement Scenario 2: Acceptance on Feature Branch. Execute `git checkout -b test_isolation_dummy_branch`, run `spawn_coder.py` with `SDLC_TEST_MODE=true`, assert exit code `0` and mock success output. Cleanup the dummy branch.
4. Hook `scripts/test_branch_isolation.sh` into `preflight.sh` to run on every build.