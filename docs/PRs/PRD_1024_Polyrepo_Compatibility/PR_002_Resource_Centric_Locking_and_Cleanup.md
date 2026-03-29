status: open

# PR-002: Resource-Centric Locking with Liveness Checks & Autonomous Cleanup

## 1. Objective
Implement resource-centric JSON locking with active liveness checks and an autonomous cleanup mechanism to safely quarantine dead pipelines.

## 2. Scope (Functional & Implementation Freedom)
- Modify the locking mechanism to key locks by project name (`locks/<ProjectName>.lock`) instead of PRD name.
- Ensure the lock file contains a JSON payload with the Orchestrator's Process ID (`PID`) and the absolute path to the target repository (`active_workdir`).
- Implement an autonomous `--cleanup` command that scans all lock files, parses the JSON payload, and performs an OS-level liveness check (e.g., `os.kill(pid, 0)`).
- If the liveness check fails (pipeline is dead), execute a forensic quarantine protocol in the `active_workdir` and safely delete the stale lock file. Skip alive pipelines.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- Lock files are correctly created per project and contain valid JSON with `PID` and `active_workdir`.
- The cleanup command accurately distinguishes between alive and dead processes using liveness checks.
- Dead pipelines trigger quarantine and lock removal; alive pipelines are left untouched.
- All associated integration tests are updated to mock and assert the new lock logic, and all tests pass (GREEN).