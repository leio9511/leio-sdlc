status: open

---
status: open
type: feature
priority: high
dependencies: []
---

# PR 1: Update Test Sandbox and Sub-agent Stubs for New CLI Signatures

## Goal
Update the Orchestrator's CLI definition and test mock stubs to accept and assert the new mandatory arguments (`--workdir` and `--prd-file`).

## Tasks
1. Update `scripts/orchestrator.py` `argparse` definition to accept `--prd-file` (required).
2. Update `scripts/test_orchestrator_fsm.sh` to pass `--prd-file dummy_prd.md` when executing `orchestrator.py`.
3. Update the fake mock stub scripts inside `scripts/test_orchestrator_fsm.sh`:
   - `spawn_coder.py` must assert that `--workdir` and `--prd-file` are present in `sys.argv`. If missing, `sys.exit(1)` with "FATAL: Coder missing mandatory args".
   - `spawn_planner.py` must assert that `--workdir` and `--prd-file` are present when invoked with `--slice-failed-pr`.
   - `spawn_reviewer.py` and `spawn_arbitrator.py` must assert that `--workdir` and `--pr-file` are present.