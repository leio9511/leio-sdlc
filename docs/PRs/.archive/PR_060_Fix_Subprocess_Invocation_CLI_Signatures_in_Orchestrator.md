status: open

---
status: open
type: bugfix
priority: high
dependencies: ["PR 1"]
---

# PR 2: Fix Subprocess Invocation CLI Signatures in Orchestrator

## Goal
Update all sub-agent subprocess invocations inside `scripts/orchestrator.py` to seamlessly pass the correct, up-to-date arguments, fulfilling the assertions established in PR 1.

## Tasks
1. **State 3 (Coder)**: Remove `--repo-dir`. Add `--workdir <workdir>` and `--prd-file <args.prd_file>`. Keep `--pr-file <current_pr>`.
2. **State 4 (Reviewer/Arbitrator)**: Remove `--repo-dir`. Add `--workdir <workdir>`. Keep `--pr-file <current_pr>`.
3. **State 5 (Planner - Tier 2 Slicing)**: Remove `--repo-dir`. Add `--workdir <workdir>` and `--prd-file <args.prd_file>`. Pass the failing PR to `--slice-failed-pr`.
4. Ensure `./preflight.sh` successfully passes (i.e., `✅ PREFLIGHT SUCCESS`) when `scripts/test_orchestrator_fsm.sh` is executed via preflight.