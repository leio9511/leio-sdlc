# Architectural Audit Report: PRD-1021 v3
**Auditor:** Senior Architecture Auditor (Independent)
**Target:** `leio-sdlc` Local Clone Sandbox Architecture
**Verdict:** 🚨 **REJECTED (FATAL FLAWS DETECTED)** 🚨

PRD-1021 v3 attempts to solve concurrency by introducing "Local Clones" while maintaining the main workspace as the ultimate source of truth. However, the proposed architecture demonstrates a fundamental misunderstanding of concurrent Git operations, POSIX filesystem behavior, and isolated state management. 

If this is implemented as written, **it will corrupt the main repository's Git index, leak state across isolated sandboxes, and result in catastrophic CI deadlocks.**

Here is the devastatingly critical breakdown of the hidden flaws:

### 1. The `git merge` Race Condition (The "Concurrency Illusion")
**The Flaw:** Requirement 7 dictates removing the global lock and replacing it with a PRD-specific lock (`.sdlc_run_<PRD_FILENAME>.lock`). Requirement 4 states that the Orchestrator will change directories back to the main repository and execute `git merge <feature_branch>`.
**The Devastation:** You have multiple Orchestrator processes running concurrently, each holding a *different* PRD lock. If Orchestrator A and Orchestrator B both complete State 5 simultaneously, they will **both `cd` to the main repository and run `git merge` at the exact same time.**
Git cannot handle concurrent modifications to the same working tree and `.git/index`. One process will hit a `.git/index.lock` error and crash, leaving the feature branch unmerged. Worse, if the merge requires a working tree update, concurrent working tree modifications will corrupt files.
**The Fix:** You *must* introduce a **Global Merge Lock** (e.g., `.sdlc_global_merge.lock`) that is acquired *only* during State 6 (Fetch, Rebase, Push, Merge) to serialize writes back to the main repository.

### 2. The `cp -al` (Hardlink) Isolation Breach
**The Flaw:** Requirement 2 mandates `cp -al` (hardlinks) for static dependencies like `node_modules` and `venv` to hydrate the sandbox.
**The Devastation:** Hardlinks share the identical underlying inode on the filesystem. If a Coder agent in Sandbox A runs `npm install <package>` or a Python script updates a `.pyc` or module inside the `venv`, it is physically modifying the files in the **main workspace** and **Sandbox B's workspace**. 
This is not isolation; this is a shared memory space masquerading as a sandbox. When one agent introduces a broken dependency or edits a vendored file, it will instantly poison all concurrent pipelines and the host environment.
**The Fix:** You cannot use hardlinks for directories that the LLM agent might mutate. You must use `cp -R` (copy), rely on Git Worktrees (with their native node_modules vacuum handled via symlinks to a protected read-only cache), or use overlayfs. 

### 3. Artifact Clobbering in the Host Repo
**The Flaw:** Requirement 3 forces `Review_Report.md` and `.coder_state.json` to be written directly to absolute paths in the *main repository*.
**The Devastation:** Since multiple Orchestrators are running concurrently without a global lock, Sandbox A and Sandbox B will overwrite each other's `.coder_state.json` and `Review_Report.md` in the main repo root. 
If Orchestrator A triggers the Reviewer, and Orchestrator B writes its Review Report to the same file 2 seconds later, Orchestrator A will read B's review. The pipelines will hallucinate and act on each other's reviews, merging code that was rejected or rejecting code that LGTM'd.
**The Fix:** Artifacts MUST be dynamically named per-session/PRD (e.g., `Review_Report_<PR_ID>_<PRD_NAME>.md`) or written *inside* the isolated sandbox, then read by the Orchestrator before teardown.

### 4. Sub-Agent Session Key Collisions (`spawn_coder.py`)
**The Flaw:** Look at the current `spawn_coder.py` logic: `session_key = f"sdlc_coder_{pr_id}"`. 
**The Devastation:** PR IDs are sliced linearly (e.g., `PR_001`, `PR_002`). If PRD-A and PRD-B both have a `PR_001.md`, both orchestrators will spawn a coder using the session key `sdlc_coder_PR_001`. 
OpenClaw will route messages from Pipeline A into Pipeline B's Coder session. The agent will receive two completely different sets of instructions and codebases, causing catastrophic hallucinations and rapid tier-3 escalation failure.
**The Fix:** The `session_key` MUST be cryptographically unique or namespace-bound to the PRD: `f"sdlc_coder_{prd_name}_{pr_id}"`.

### 5. Pushing to a Non-Bare Active Repository
**The Flaw:** Requirement 4 mandates `git push origin <feature_branch>` from the sandbox to the host repo. 
**The Devastation:** Pushing to a non-bare Git repository (the main workspace) is fraught with edge cases. While pushing a *new* branch is generally allowed, if the main repo happens to have that branch checked out (e.g., a dev inspecting it), the push will be rejected by `receive.denyCurrentBranch`. Additionally, concurrent pushes to the same origin `.git` directory from multiple sandboxes can cause `refs/` lock contention.
**The Fix:** The Orchestrator should not `push` from the sandbox. Instead, the Orchestrator (running in the main repo context) should fetch the branch directly from the sandbox via `git fetch .sandboxes/<PRD_NAME> <feature_branch>:<feature_branch>`, completely bypassing non-bare push restrictions.

### Summary
Do NOT implement PRD-1021 v3. It creates an illusion of concurrency while relying on non-thread-safe filesystem and Git mechanics. Return to the drawing board, implement a localized state model, serialize your Git commits to the origin, and fix the namespace collisions.
