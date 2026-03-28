# PRD: Implement Automated Teardown & Clean-up for Orchestrator Aborts (ISSUE-1039)

## Context
When the SDLC `orchestrator.py` script executes normally but a sub-agent (Coder) fails verification, the Orchestrator has an internal `State 5` mechanism that correctly resets and deletes the failing branch. 
However, if the `orchestrator.py` script *itself* crashes (e.g., Python exception, missing parameters), or if it is forcibly killed via a system signal (e.g., `SIGTERM`, `SIGINT` / Ctrl+C), it abruptly terminates. This leaves the Git repository in a "dirty" and unpredictable state: checked out on a temporary branch, files left modified, and untracked artifacts littered in the workspace.

This forces the human operator (or the main Agent) to manually intervene and execute raw Git commands (like `git checkout master` and `git reset --hard`) to recover the workspace. With the newly introduced Pre-Commit Hook (ISSUE-1012), this manual cleanup process becomes even more cumbersome. We must provide an automated, foolproof cleanup mechanism.

## Requirements

1. **Global Exception Handling (The `try...finally` block)**:
   - Refactor `scripts/orchestrator.py` to wrap its entire execution loop inside a high-level `try...finally` block.
   - The `finally` block must gracefully handle resetting the workspace back to `master` if (and only if) the Orchestrator exits with a non-zero status or fails to complete normally.
   - The teardown sequence MUST execute: `git reset --hard HEAD`, `git clean -fd`, and `git checkout master` (with forced branch deletion for the currently executing PR branch if it exists).

2. **Signal Handling (`SIGINT` & `SIGTERM`)**:
   - The Python script must use the `signal` module to intercept `SIGINT` (Ctrl+C) and `SIGTERM` (Kill commands).
   - Upon receiving a termination signal, the script must immediately trigger the teardown cleanup sequence before exiting.

3. **Standalone Cleanup Flag (`--cleanup`)**:
   - Add a new command-line argument `--cleanup` to `orchestrator.py`.
   - When executed with `python3 scripts/orchestrator.py --cleanup`, the script should bypass the normal SDLC pipeline and immediately run the global teardown sequence described above, then exit gracefully. 
   - This provides the Manager/human with a deterministic, "safe" tool to reset a corrupted environment without typing raw Git commands.

## Framework Modifications
- `scripts/orchestrator.py`

## Architecture
This relies on deep integration with Python's context management and OS signal handling to guarantee a clean workspace regardless of how the script terminates. By centralizing the cleanup logic into a single function, the `--cleanup` flag can seamlessly invoke the same recovery routine used by the `finally` block and signal handlers.

## Acceptance Criteria
- [ ] Throwing a forced Python exception mid-execution correctly triggers a full Git reset and returns to `master`.
- [ ] Sending a `SIGTERM` to a running `orchestrator.py` successfully cleans the directory before the process dies.
- [ ] Running `python3 scripts/orchestrator.py --cleanup` instantly restores the repository to a clean `master` state.