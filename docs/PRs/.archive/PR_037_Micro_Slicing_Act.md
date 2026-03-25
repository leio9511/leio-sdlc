# PR_037_Micro_Slicing_Act.md

status: closed
dependencies: []

## Goal
Implement the strict E2E test to verify Planner micro-slicing behavior and update the Planner's system prompt to enforce the Micro-Slicing Act, ensuring the CI pipeline remains green.

## Tasks (TDD Local Closed-Loop)
1. **Write Test (Red Phase)**: Create `scripts/test_planner_micro_slicing.sh`.
   - Set up a sandbox environment (`mkdir -p /tmp/planner_sandbox/prs`).
   - Generate a `dummy_complex_prd.md` in the sandbox that describes a multi-tier feature.
   - Execute the Planner script: `python3 scripts/spawn_planner.py --prd-file dummy_complex_prd.md --out-dir /tmp/planner_sandbox/prs`.
   - Add assertions: Count `.md` files in output dir (assert > 1). Loop through them and `grep -q "status: closed"`. Verify alphabetical sorting prefixes.
   - Append `bash scripts/test_planner_micro_slicing.sh` to the execution block in `preflight.sh`.
   - Run `./preflight.sh` locally and verify it fails (Red).

2. **Write Implementation (Green Phase)**:
   - Locate the Planner's system prompt in `scripts/spawn_planner.py`.
   - Inject the **Core Instruction**: *"You are forbidden from generating a single monolithic PR contract. You must break the PRD down into a sequential, dependency-ordered chain of Micro-PRs. You MUST use `python3 scripts/create_pr_contract.py --job-dir ... --title ... --content-file ...` to generate the PR contracts instead of raw file writing."*
   - Explicitly mandate that EVERY generated PR contract must include `status: closed`.

3. **Verify and Commit**:
   - Run `./preflight.sh` locally. Fix any issues until it outputs `✅ PREFLIGHT SUCCESS`.
   - **Only commit when green.** Do not commit the red phase separately.