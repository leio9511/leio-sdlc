status: open

# PR Contract: PRD-054-01 - Orchestrator CLI & State 0 Logic
title: PRD-054-01 - Orchestrator CLI & State 0 Logic
status: open
slice_depth: 0

## 1. Goal
Implement State 0 in `scripts/orchestrator.py` to support automated PRD ingestion and idempotency checks.

## 2. Requirements
- Update `argparse` in `scripts/orchestrator.py` to include `--prd-file` and `--force-replan`.
- Implement State 0 logic:
    - If `--prd-file` is set, check `docs/PRs/` for existing PRs referencing the PRD.
    - If `--force-replan` is false and existing PRs are found, skip State 0.
    - Otherwise, run `scripts/spawn_planner.py --prd-file <PATH>`.
    - Validate that at least one `status: open` PR was generated in `docs/PRs/`.
    - Handle Planner failure (count == 0) by exiting with FatalError.
- Ensure transition from State 0 to State 1.

## 3. Files to Modify
- `scripts/orchestrator.py`

## 4. Verification
- Run `scripts/orchestrator.py --prd-file <TEST_PRD>` and verify it calls the planner.
- Verify idempotency by running it again without `--force-replan`.
