status: closed

# PR-001: Fix Git Tracking & Subprocess Parameters

## 1. Objective
Remove explicit git tracking of the internal runs directory to prevent git pollution, and fix a parameter mismatch bug in the code merging subprocess.

## 2. Scope (Functional & Implementation Freedom)
- Remove explicit `git add` and `git commit` commands that target the internal state tracking folder (e.g., inside the State 5 Tier 1 fallback block) to prevent polluting the git history. Do not perform a blanket removal of all git commands.
- Ensure absolutely no auto-commit logic exists in the approval blocks.
- Remove the unsupported `--run-dir` argument from all subprocess calls to the code merging script.
- Update any existing tests (such as immutability tests) to align with the removed git tracking behavior, ensuring they test the actual new logic legitimately without reward hacking.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The orchestration script executes without Guardrail violations regarding git tracking of the internal runs directory.
2. The code merging subprocess executes successfully without crashing due to invalid arguments.
3. The Coder MUST ensure all tests run GREEN before submitting, including legitimately repaired tests that previously relied on the removed git tracking logic.