status: open

---
title: "PR 2: Update Orchestrator CLI Arguments and Subprocess Invocations"
status: open
dependencies: ["PR 1: Update Orchestrator Test Stubs for New CLI Signatures (TDD)"]
---

# PR 2: Update Orchestrator CLI Arguments and Subprocess Invocations

## Context
Following PR 1 (TDD Test Update), the test suite now correctly expects sub-agents to be invoked with the new CWD Guardrail signatures. The orchestrator must be updated to pass these assertions.

## Requirements
1. Modify `scripts/orchestrator.py`:
   - Add `--prd-file` (required) to `argparse`.
   - Update `subprocess.run` calls in **State 3 (Coder)**: Remove `--repo-dir`, add `--workdir <workdir>` and `--prd-file <args.prd_file>`. Keep `--pr-file <current_pr>`.
   - Update `subprocess.run` calls in **State 4 (Reviewer)**: Remove `--repo-dir` (if present), add `--workdir <workdir>`. Keep `--pr-file <current_pr>`.
   - Update `subprocess.run` calls in **State 4 (Arbitrator)**: Ensure `--workdir` and `--pr-file` are passed correctly.
   - Update `subprocess.run` calls in **State 5 (Planner - Tier 2 Slicing)**: Remove `--repo-dir`, add `--workdir <workdir>`, ensure `--prd-file <args.prd_file>` is passed. Note: Tier 2 slicing passes `current_pr` as the failing PR (`--slice-failed-pr current_pr`), so `--prd-file` still needs to point to the actual PRD.

## Acceptance Criteria
- Running `scripts/test_orchestrator_fsm.sh` MUST pass.
- Running `./preflight.sh` MUST complete with `✅ PREFLIGHT SUCCESS`.
