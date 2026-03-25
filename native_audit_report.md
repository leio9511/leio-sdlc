**Architectural Audit Report: PRD-1021 v3 (Local Clone Sandbox Architecture)**
**Auditor:** Senior Architecture Auditor
**Target Project:** `leio-sdlc` (Orchestrator)
**Status:** **REJECTED - FATAL ARCHITECTURAL FLAWS DETECTED**

After a devastatingly critical review of the proposed PRD-1021 v3 against the current `orchestrator.py` implementation, I have identified multiple catastrophic failure points. This architecture is structurally unsound, fundamentally misinterprets how Git concurrency works, and will introduce insidious data corruption and deadlocks if implemented. 

Here are the fatal flaws broken down by PRD requirement:

### 1. Global `.git/index.lock` Collision in State 6 (Merge Routing)
* **The Flaw (Requirement 4 & 7):** The PRD replaces the global `.sdlc_run.lock` with granular `.sdlc_run_<PRD>.lock` files, but still mandates that every sandbox `cd` back to the shared main repository to execute `git merge <feature_branch>`.
* **Why it's devastating:** While the *development* phase is sandboxed, the *merge* phase relies on a shared, global mutable state (the main repository's working tree). If Orchestrator A and Orchestrator B complete their PRs concurrently, they will both switch back to the main repository and simultaneously execute `git merge`. Git will instantly throw a `.git/index.lock` or `.git/HEAD.lock` error, crashing one or both pipelines. Granular locks do absolutely nothing to protect the shared Git index of the origin repository. 
* **The Fix:** The merge must happen via a bare push or API call. Alternatively, the orchestrator needs a short-lived, synchronous `fcntl` lock *exclusively* wrapping the State 6 `git merge` execution block in the main repo.

### 2. Hardlink Hydration (`cp -al`) Causes Global Mutability Corruption
* **The Flaw (Requirement 2):** To prevent dependency vacuum, the PRD mandates using `cp -al` (hardlinks) to hydrate static dependency directories like `node_modules` or `venv`.
* **Why it's devastating:** Hardlinks share the identical inode on the filesystem. If a Coder sub-agent inside Sandbox A executes `npm install`, `pip install`, or any build script that modifies a file inside the hardlinked `node_modules`, it will mutate that file globally across the main repository and **all other concurrent sandboxes**. This entirely breaks the isolation guarantee, leading to cross-talk, locked file errors during concurrent builds, and corrupted environments.
* **The Fix:** Use Copy-on-Write (`cp --reflink=auto`) if the filesystem supports it (Btrfs/ZFS), or use standard symlinks (`ln -s`) combined with a strict policy against mutating dependency files in the sandbox.

### 3. Main Workspace Working Tree Chaos (Requirement 8 vs Requirement 4)
* **The Flaw (Requirement 8 & 4):** Requirement 8 aggressively removes the early dirty workspace check, stating "The main workspace acts as the host and may have uncommitted files." Yet, Requirement 4 mandates executing `git merge` in this exact same workspace.
* **Why it's devastating:** You cannot reliably run `git merge` in a dirty working tree. If the main workspace has uncommitted files (as Req 8 now explicitly permits), `git merge <feature_branch>` will inevitably abort with `"error: Your local changes to the following files would be overwritten by merge"`. Furthermore, if a human user is working in the main directory and has checked out a different branch, the automated Orchestrator will merge the PR into the wrong branch.

### 4. Non-Interactive Rebase Brittle Failure (Requirement 5)
* **The Flaw (Requirement 5):** The PRD requires `git fetch origin && git rebase origin/master` in the sandbox. If a conflict occurs, it mandates `git rebase --abort` and an immediate `[FATAL_GIT]` crash.
* **Why it's devastating:** In a concurrent CI system, overlapping PRs touching adjacent lines will naturally cause merge conflicts. By forcing a fatal crash on *any* rebase conflict, PRD-1021 guarantees that concurrent SDLC runs will destroy each other's pipelines rather than triggering the existing 3-Tier Escalation Protocol (State 5). You are neutering the autonomous self-healing capability of the orchestrator.
* **The Fix:** A rebase conflict should trigger State 5, spinning up the Coder with the conflict markers to autonomously resolve the collision, exactly as it resolves Reviewer rejections.

### 5. Path Resolution Schizophrenia & State Corruption (Requirement 3)
* **The Flaw (Requirement 3):** The PRD mandates passing absolute paths for PR contracts (`--pr-file`) located in the main repo, but sub-agents execute in the sandbox. `Review_Report.md` and `.coder_state.json` must be written directly to the main repository.
* **Why it's devastating:** The current `orchestrator.py` passes `--workdir` to sub-agents. If `--workdir` points to the sandbox, how do `spawn_coder.py` and `spawn_reviewer.py` magically know the path to the main repository to write artifacts? The PRD does not introduce a `--host-dir` or `--origin-dir` parameter. The sub-agents will either write these files into the sandbox (violating the PRD) or crash trying to resolve relative paths. 
* **Worse:** In `orchestrator.py`, `set_pr_status` runs `git add <pr_file>` and `git commit` to update the status. If the orchestrator is running inside the sandbox, it will try to commit a main-repo file to the sandbox's git history, completely destroying the state tracking.

### Final Verdict
PRD-1021 v3 is **dangerously immature**. While the core idea of a local clone sandbox is valid for circumventing `git worktree` deadlocks, the execution plan fundamentally fails to manage the lifecycle of the shared main repository. Do not merge or implement this PRD until the synchronization, pathing, and hydration strategies are entirely rewritten.
