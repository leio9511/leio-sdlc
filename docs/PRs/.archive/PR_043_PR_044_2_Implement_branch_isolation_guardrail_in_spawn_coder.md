status: open

---
status: open
dependencies: ["PR_044_1"]
---
# PR_044_2: Implement branch isolation guardrail in spawn_coder.py

## Objective
Implement the branch isolation logic inside `spawn_coder.py` to prevent running on production branches.

## Tasks
1. Update `scripts/spawn_coder.py` to include branch detection using Python's `subprocess` to execute `git rev-parse --abbrev-ref HEAD` in the `--workdir`.
2. Add a fail-fast condition: if the branch is `master` or `main`, the script MUST `sys.exit(1)`.
3. Output the exact AI-actionable error to `stderr`:
   `[FATAL] Branch Isolation Guardrail: Coder agent cannot be spawned on the 'master' or 'main' branch.`
   `[ACTION REQUIRED]: You must create and checkout a new feature branch before assigning work to the Coder.`
   `Fix this by executing: git checkout -b feature/<pr_name>`
4. Verify the changes pass `scripts/test_branch_isolation.sh`.