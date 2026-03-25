status: open

## Objective
Implement foundational `--workdir` guardrails in `create_pr_contract.py` and `get_next_pr.py`, and set up TDD sandbox.

## Requirements
1. **Argparse**: Add `parser.add_argument("--workdir", required=True)` to `create_pr_contract.py` and `get_next_pr.py`.
2. **Absolute Path**: `workdir = os.path.abspath(args.workdir)`
3. **OS Lock**: `os.chdir(workdir)`
4. **Auto-Scaffolding**: `os.makedirs("docs/PRs", exist_ok=True)` in `create_pr_contract.py`.
5. **Path Traversal Defense**: In `create_pr_contract.py`, assert that the target PR file path stays inside `workdir` using `os.path.commonpath([workdir, target_path]) == workdir`. If false, raise `SecurityError`.
6. **Testing**: Create `scripts/test_cwd_guardrail.sh` with sandbox setup (`TEMP_DIR=$(mktemp -d)`, `trap 'rm -rf "$TEMP_DIR"' EXIT`). Implement T1 (Fail-Fast Missing Arg) for the 2 scripts, and T5 (Path Traversal Rejection) for `create_pr_contract.py`.
