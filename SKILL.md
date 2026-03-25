---
name: leio-sdlc
version: 0.6.0
description: >
  Execute a multi-agent Software Development Life Cycle (SDLC) framework.
  Triggers on: "start a new project", "code this feature", "review this PR", "merge the code", "resume", "handle failure".
---

# LEIO SDLC Runbook

【Job 并发隔离沙盘机制】（The Workspace-as-a-Job-Queue）
1. 规定：禁止将生成的 PR 扔到全局 `docs/PRs/` 里。所有执行任务必须在项目根目录创建 `.sdlc/jobs/<PRD_文件名（无后缀）>/` 目录。
2. 规定：Planner 生成的所有 PR 合约必须写在这个目录下。Manager 也只轮询这个目录。

【自解释纪律】：如果用户（Boss）向你提问关于 leio-sdlc 的内部逻辑、架构设计、状态机或错误处理机制，你**严禁凭空记忆或编造**。你必须立刻使用 `read` 工具读取 `ARCHITECTURE.md`，基于该说明书向用户解释。

## Queue Polling Engine (Continuous Processing)

As the Manager, you are a continuous state machine. When processing a job directory, you MUST execute a `while` loop logic:

1. Run `python3 scripts/get_next_pr.py --workdir $(pwd) --job-dir <job_dir>` to fetch the next open PR.

2. If it returns `[QUEUE_EMPTY]`, you exit your loop and report completion.

3. If it returns a PR file path, you must execute the full SDLC lifecycle for that PR:

   a) Spawn Coder (Command Template 2).

   b) Spawn Reviewer (Command Template 3).

   c) Merge Code (Command Template 4).

   d) Update Status: `python3 scripts/update_pr_status.py --pr-file <pr_file> --status closed`.

4. Repeat from step 1.



**CRITICAL CODER DELEGATION DISCIPLINE (Token-Optimized CI):**

When spawning a Coder, you MUST explicitly enforce the following rule in your delegation instructions:

"You must execute `./preflight.sh` yourself in your sandbox. If it fails (Red Phase), you must continuously fix the code and re-run `./preflight.sh` until it outputs `✅ PREFLIGHT SUCCESS`. Absolutely NO returning to the Manager with red lights or failing tests!"


This skill provides a multi-agent Software Development Life Cycle (SDLC) framework for OpenClaw. It replaces theoretical API endpoints with explicit, copy-pasteable bash command templates.

**STRICT DIRECTIVE TO MANAGER:**
You MUST copy these commands exactly into your `exec` tool. Do not invent your own `sessions_spawn` arguments.
**WARNING:** The Manager MUST NOT use code modification tools (`edit`, `write`, or shell text manipulation like `sed`, `awk`, `echo >`) to fix code directly. All code fixes MUST be routed back to the Coder via a "Revision" state.

## Command Template 1: Spawning a Planner (Plan)
Use this to generate PR Contracts based on PRDs.
**PRE-CONDITION GUARD:** The pipeline's ONLY valid entry point is an existing `PRD_*.md` file path. The Manager MUST physically verify the existence of a `PRD_*.md` file in `docs/PRDs/`. You are NOT a Product Manager and MUST NOT generate PRDs from dialogue. The first step is to read the existing PRD, and then spawn the Planner.

To spawn a planner, use the `exec` tool to run: `python3 {baseDir}/scripts/spawn_planner.py --prd-file <path_to_prd>`

## Command Template 2: Spawning a Coder (Code)
Use this to execute coding tasks based on PR Contracts.

To spawn a coder, use the `exec` tool to run: `python3 {baseDir}/scripts/spawn_coder.py --pr-file <path_to_pr> --prd-file <path_to_prd>`

## Command Template 2b: Spawning a Coder for Revision (Correction Loop)
`python3 {baseDir}/scripts/spawn_coder.py --pr-file <path_to_pr> --prd-file <path_to_prd> --feedback-file <path_to_review_report>`

If the Reviewer generates a `Review_Report.md` containing `[ACTION_REQUIRED]`, do NOT merge. You must execute a Correction Loop: run the Coder Revision command (Command Template 2b), then run the Reviewer command again. Repeat this loop up to MAX_REVISIONS times (default 5, unless instructed otherwise) or until `[LGTM]` is given.

## Command Template 3: Start Review Session (Review)
Use this to review code changes against the PR Contract.
To spawn a reviewer, use the `exec` tool to run: `python3 {baseDir}/scripts/spawn_reviewer.py --pr-file <path_to_pr> --diff-target <base_hash>..<latest_hash>`

## Command Template 4: Merge and Deploy (Merge)
Use this to merge approved changes into the master branch.
**PRE-CONDITION GUARD:** The Manager MUST verify that a Reviewer has reviewed the specific commit hash and issued an "Approved" status. Merging without a Reviewer's explicit approval is a critical violation.
To merge approved code, use the `exec` tool to run: `python3 {baseDir}/scripts/merge_code.py --branch <branch_name> --review-file <path_to_review_report> [--force-lgtm]`
Manager has Override Authority. If the Reviewer is stuck in an infinite nitpicky loop giving `[ACTION_REQUIRED]`, you can pass `--force-lgtm` to bypass the `[LGTM]` requirement and merge anyway.

## Command Template 5: Issue Tracking

To update an issue status, use the `exec` tool to run: `python3 {baseDir}/scripts/update_issue.py --issue-id <ID> --status <new_status>`
