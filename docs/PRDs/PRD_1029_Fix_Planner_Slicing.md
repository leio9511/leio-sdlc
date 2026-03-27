# PRD: Fix Planner PR Slicing Ordering (ISSUE-1029)

## Context
When a PR fails the SDLC pipeline, it is escalated (State 5) and sent to the Planner for re-slicing (breaking into Micro-PRs). Currently, the Planner is re-slicing failed PRs (e.g., PR_001) but the resulting Micro-PRs are appended to the end of the job queue (e.g., PR_003, PR_004). This breaks sequential execution because PR_002 will execute before the fixes for PR_001. 

The underlying problem is that `spawn_planner.py` does not inject the `--insert-after <id>` parameter into the instructions given to the Planner agent for `create_pr_contract.py`. 

## Requirements
- The Planner script (`scripts/spawn_planner.py`) must extract the failed PR's prefix (e.g., `001` from `PR_001_xxx.md` or `002_1` from `PR_002_1_xxx.md`) when `--slice-failed-pr` is provided.
- The Planner's system prompt MUST be updated to explicitly append `--insert-after {failed_pr_id}` to the `python3 create_pr_contract.py` command template.
- The prompt must clearly state that `--insert-after {failed_pr_id}` is a MANDATORY flag to ensure sequential ordering of generated PRs.
- The fix should use Python's `re` module to cleanly extract the ID pattern `r"^PR_(\d+(?:_\d+)*)_"` from the basename.

## Framework Modifications
- `scripts/spawn_planner.py`

## Architecture
The update touches the core orchestrator sub-agent spawn script `scripts/spawn_planner.py`. It reads the argument from `--slice-failed-pr`, extracts the identifier, and embeds it strictly into the instruction payload sent to the LLM backend for tool execution.

## Acceptance Criteria
- [ ] `scripts/spawn_planner.py` is successfully updated to extract the PR ID using regex.
- [ ] The `task_string` prompt sent to the Planner agent includes the `--insert-after` parameter automatically when a PR fails.
- [ ] Running `test_planner_slice_failed_pr.sh` passes successfully.