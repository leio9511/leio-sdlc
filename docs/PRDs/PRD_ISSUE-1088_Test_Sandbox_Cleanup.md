---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/.openclaw/workspace/projects/leio-sdlc
---

# PRD: ISSUE-1088 Fix Test Sandbox Leakage & Auto-Cleanup

## 1. Context & Problem (业务背景与核心痛点)
Currently, several shell-based test scripts (e.g., `test_planner_micro_slicing.sh`, `test_manager_queue_polling.sh`) create temporary sandbox directories in `tests/planner_sandbox_$$` using the process ID ($$). However, these scripts lack a `trap` or `rm` command at the end to clean up these directories. As a result, every time CI or a developer runs the tests, a new "ghost" directory is left behind, leading to long-term storage bloat and workspace pollution.

## 2. Requirements & User Stories (需求定义)
- **R1: Retroactive Cleanup**: Identify and delete all existing `tests/planner_sandbox_*` and `tests/manager_sandbox_*` directories.
- **R2: Automated Leakage Prevention**: Modify the testing scripts to ensure they automatically delete their own sandbox directories upon completion (success or failure).

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Deletion Phase**: Coder will create a script `scripts/cleanup_test_sandboxes.sh` to safely prune all legacy sandbox directories from `tests/`. 
    - **CRITICAL**: The script MUST use defensive checks before executing `rm -rf`. 
    - **CRITICAL ANTI-MICRO-SLICING GUARDRAIL**: The legacy sandboxes (`tests/planner_sandbox_*` etc.) are actually **NOT tracked in Git**. Therefore, running the cleanup script will NOT produce any Git diff. Do NOT create a separate PR just to "execute" the script, because an empty diff will cause the Reviewer to reject it and trigger infinite micro-slicing. 
    - **Instead**, the Coder should simply write the `cleanup_test_sandboxes.sh` script and update the test scripts in the SAME PR, and verify them locally.
- **Script Hardening**:
    - Update `scripts/test_planner_micro_slicing.sh` and `scripts/test_manager_queue_polling.sh`.
    - Implement a defensively coded `trap` pattern at the start of these scripts: `trap '[[ -n "$SANDBOX" ]] && rm -rf "$SANDBOX"' EXIT`. This ensures the temporary directory is wiped upon script termination without risking undefined variable expansion.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario: Test Sandbox Self-Destruction**
    - **Given** I run `bash scripts/test_planner_micro_slicing.sh`
    - **When** the script completes (Pass or Fail)
    - **Then** the directory `tests/planner_sandbox_<PID>` must NO LONGER exist on the filesystem.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Validation**: Run the modified test scripts and manually verify with `ls` that no new sandbox directories are created post-execution.
- **Regression**: Ensure `preflight.sh` passes to confirm the `trap` logic doesn't interfere with exit codes.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/cleanup_test_sandboxes.sh` (Create)
- `scripts/test_planner_micro_slicing.sh`
- `scripts/test_manager_queue_polling.sh`
- **NOTE ON LEGACY SANDBOXES**: The legacy sandboxes are NOT tracked in Git. The Coder should NOT expect `git rm -r` to work on them, and the Reviewer should NOT expect to see their deletion in the Git diff.

## 7. Hardcoded Content (硬编码内容)
- `trap '[[ -n "$SANDBOX" ]] && rm -rf "$SANDBOX"' EXIT`

## 8. Rollback / Feature Flag Strategy (回滚策略)
- **Rollback**: Since this involves deletion and CI script modification, Git is the primary rollback mechanism. Any structural damage to the CI pipeline can be reverted via `git revert`. NOTE: The legacy sandboxes were accidentally committed to the repo, so the cleanup script (or the Coder directly) must execute `git rm -r` to remove them from Git tracking.
