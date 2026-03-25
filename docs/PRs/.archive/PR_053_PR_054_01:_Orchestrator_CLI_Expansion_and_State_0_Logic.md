status: open

# PR_054_01: Orchestrator CLI Expansion and State 0 Logic

## Goal
Implement the core CLI expansion and State 0 (PRD Ingestion) logic in `scripts/orchestrator.py`.

## Tasks
1. Update `argparse` to include `--prd-file` and `--force-replan`.
2. Implement the `State 0` logic at the beginning of the `main()` function:
    - If `--prd-file` is set, perform an idempotency check:
        - Scan `docs/PRs/*.md` for the PRD filename in the metadata (or simply check if any `open` PRs exist if we want a simpler heuristic, but the PRD says "mention this PRD in their metadata"). *Self-correction*: The PRD says "Scan `docs/PRs/` for any existing PRs that mention this PRD in their metadata."
    - If no active PRs match and no force replan, invoke `scripts/spawn_planner.py --prd-file <PATH>`.
    - Validate that at least one `status: open` PR was generated.
    - Transition to State 1.
3. Ensure error bubbling from `spawn_planner.py`.

## Verification (TDD)
- Update `scripts/test_orchestrator_fsm.sh` with the following scenarios:
    - Pure State 0 Start.
    - Idempotency (Resume).
    - Elastic Slicing (Single PR success).
    - Planner Failure (Zero PRs).

## Constraints
- Use `subprocess.run` for script invocation.
- Halt with `sys.exit(1)` on fatal errors.
