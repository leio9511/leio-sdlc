status: open

# PR-001: Remove Obsolete PR Contract Auto-Commit Logic

## 1. Objective
Remove the obsolete logic in the SDLC orchestrator that attempts to auto-commit PR contracts when checking out branches, preventing accidental commits of unrelated staged files.

## 2. Scope (Functional & Implementation Freedom)
- Locate the state machine loop within the orchestrator execution flow.
- Find the section (near "State 2" or branch checkout) that checks for staged changes (`git diff --cached`) and automatically creates a commit with a message like "docs(planner): auto-generated PR contracts".
- Completely remove this auto-commit block and its associated condition.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The Orchestrator successfully runs the State Machine without attempting to commit "auto-generated PR contracts" during the relevant state or branch checkout phase.
2. PR status updates must persist on the filesystem even after the orchestrator performs a `git reset --hard HEAD`.
3. The Coder MUST ensure all existing tests pass (`GREEN`) and, if applicable, update or remove any tests that assert the presence of this auto-commit step.