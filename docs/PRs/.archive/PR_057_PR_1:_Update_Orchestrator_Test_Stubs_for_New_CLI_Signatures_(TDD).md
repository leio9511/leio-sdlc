status: open

---
title: "PR 1: Update Orchestrator Test Stubs for New CLI Signatures (TDD)"
status: open
dependencies: []
---

# PR 1: Update Orchestrator Test Stubs for New CLI Signatures (TDD)

## Context
As part of PRD-058, the orchestrator needs to pass updated CLI arguments to sub-agents (`--workdir` instead of `--repo-dir`, and newly required `--prd-file`). Following TDD, this first PR updates the test sandbox to enforce these new signatures.

## Requirements
1. Modify `scripts/test_orchestrator_fsm.sh`:
   - Update the invocation of `orchestrator.py` in the test script to include `--prd-file dummy_prd.md`.
   - Update the mock stub scripts generated within the test (`spawn_coder.py`, `spawn_reviewer.py`, `spawn_arbitrator.py`, `spawn_planner.py`):
     - **Coder Stub**: Assert `--workdir` and `--prd-file` are present in `sys.argv`. Exit 1 with "FATAL: Coder missing mandatory args" if missing.
     - **Planner Stub**: Assert `--workdir` and `--prd-file` are present when invoked with `--slice-failed-pr`. Exit 1 if missing.
     - **Reviewer & Arbitrator Stubs**: Assert `--workdir` and `--pr-file` are present. Exit 1 if missing.

## Acceptance Criteria
- Running `scripts/test_orchestrator_fsm.sh` should now FAIL (because the orchestrator implementation is not yet updated), but the assertions must be correctly placed.
