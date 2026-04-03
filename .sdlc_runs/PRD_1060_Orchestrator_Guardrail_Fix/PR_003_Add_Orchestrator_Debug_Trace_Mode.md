status: in_progress

# PR-003: Add Orchestrator Debug Trace Mode

## 1. Objective
Enhance orchestrator observability by adding an optional debug trace mode for state transitions and subprocess calls.

## 2. Scope (Functional & Implementation Freedom)
- Add a new `--debug` CLI argument to the main orchestrator script.
- When `--debug` is enabled, the script should output detailed trace logs for state transitions and subprocess executions.
- The default execution behavior (without `--debug`) must remain silent.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The orchestrator script accepts the `--debug` flag successfully.
2. Executing with `--debug` produces detailed trace output for state transitions and subprocesses.
3. Executing without `--debug` remains silent as per the standard baseline.
4. The Coder MUST ensure all tests run GREEN before submitting.