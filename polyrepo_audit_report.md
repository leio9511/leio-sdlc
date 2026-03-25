/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: get_next_pr.py: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: --prd-file: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: --workdir: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: /root/.openclaw/workspace/docs/PRDs/: Is a directory
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: workdir: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: /projects/AMS: No such file or directory
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: spawn_planner.py: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: --workdir: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: --prd-file: command not found
/root/.openclaw/workspace/projects/leio-sdlc/spawn_native_auditor.sh: line 9: .gitignore: command not found
**ARCHITECTURAL AUDIT REPORT**
**SUBJECT:** Hub & Spoke Polyrepo Architecture Proposal vs. Current `leio-sdlc` Implementation
**STATUS:** **CRITICAL FAILURE PREDICTED**

After a rigorous inspection of the proposed Polyrepo architecture plan and the existing `leio-sdlc` source code (`orchestrator.py`, `spawn_planner.py`, `spawn_coder.py`), I have identified several devastating architectural flaws. If this plan is executed without major codebase refactoring, the SDLC pipeline will suffer from immediate path traversal crashes, Git boundary collapses, and global lock contention.

Here is the unvarnished breakdown of why the current code will catastrophically fail under the Hub & Spoke Polyrepo model.

### 1. Pre-Flight Pathing Misalignment (The Global Context Bleed)
The orchestrator script fundamentally misunderstands its execution context. In `orchestrator.py`, critical pre-flight checks are executed **before** `os.chdir(workdir)` is called:
```python
# Executed before os.chdir(workdir)!
branch_output = subprocess.run(["git", "branch", "--show-current"], ...)
lock_fd = os.open(".sdlc_run.lock", os.O_CREAT | os.O_RDWR)
status_output = subprocess.run(["git", "status", "--porcelain"], ...)
```
* **Impact A (False Positives):** The `git branch` and `git status` checks will evaluate the *caller's* directory (the global `/root/.openclaw/workspace`), NOT the target spoke repository (`projects/AMS`). If the global workspace is dirty or not on `master`, the orchestrator will fatally abort, refusing to process a perfectly clean, isolated sub-repo.
* **Impact B (Global Lock Contention):** The `.sdlc_run.lock` file is created in the global workspace. True Polyrepo architecture implies parallel development in independent spokes. Because the lock file is global, you **cannot run SDLC on `projects/AMS` and `projects/ClawOS` simultaneously**. The second orchestrator will crash with *"Another SDLC pipeline is currently running"*, completely negating the parallelization benefits of a Polyrepo.

### 2. Git Boundary Collapse (The Missing `.git` Trap)
The plan dictates: *"Each folder in `projects/` will run `git init` and become an entirely independent Git repository."*
However, `orchestrator.py` possesses **zero validation** to verify that `--workdir` is actually an initialized Git repository.
* **The Catastrophic Edge Case:** If a human or script forgets to run `git init` inside `projects/AMS`, Git commands executed inside that directory will traverse *up* the directory tree until they find the global `/root/.openclaw/workspace/.git` repository.
* **The Chain Reaction:** Because `projects/` is added to the global `.gitignore`, the orchestrator's automated `git add` commands (e.g., staging `PR_001.md`) will fatally crash with a Git ignore error. If forced, the orchestrator will start checking out feature branches (`projects/AMS/PR_001`), committing code, and executing merges **directly against the global repository**, thoroughly polluting it and destroying the Polyrepo isolation boundary.

### 3. Rigid Workspace Locking vs. Global PRD Injection
In `spawn_planner.py` and `spawn_coder.py`, the AI agents are prompted with a strict boundary constraint:
> *"ATTENTION: Your root workspace is rigidly locked to {workdir}. You are strictly forbidden from reading, writing, or modifying files outside this absolute path."*

Simultaneously, the Orchestrator feeds the agents an absolute path to a global PRD file (e.g., `/root/.openclaw/workspace/docs/PRDs/PRD_xxx.md`) that exists *outside* of `--workdir`.
* **Impact:** While the initial prompt injects the `prd_content` directly, if the Planner or Coder attempts to use a tool to dynamically re-read the PRD file (or verify referenced assets in the PRD folder) during complex reasoning loops, their tool calls will be explicitly blocked or rejected by their own prompt instructions because the PRD path violates their rigid `workdir` lock. 

### 4. Broken Scaffolding Inheritance
In `spawn_planner.py`, there is dynamic scaffolding logic:
```python
SDLC_DIR = os.path.dirname(os.path.abspath(__file__))
# Copies .gitignore from SDLC_DIR/.. to workdir
```
* **Impact:** If `leio-sdlc` itself is moved into `projects/leio-sdlc/` as a spoke repository, `SDLC_DIR/..` will point to the root of the `leio-sdlc` repository, not the global workspace root. If the global scaffolding templates (`.gitignore`, `.sdlc_guardrail`) are left in the global repository (e.g., `/root/.openclaw/workspace/TEMPLATES`), the planner will fail to find and copy them, leaving new spoke repositories without their mandatory SDLC guardrails.

### Recommendations for Mitigation:
1. **Move `os.chdir(workdir)` to the absolute top** of `orchestrator.py` `main()`, immediately after parsing arguments, so all lock files and Git validations occur *inside* the spoke.
2. **Add a hard boundary check:** `if not os.path.exists(os.path.join(workdir, ".git")): sys.exit("[FATAL] Sub-repo is not a Git repository.")`
3. **Re-architect Asset Scoping:** Copy the target `PRD_xxx.md` file *into* the spoke repository (e.g., `projects/AMS/docs/PRDs/`) before spawning agents, so all reads and writes are safely contained within the locked `workdir`.
4. **Update Template Paths:** Hardcode or pass an explicit `--template-dir` argument pointing to the global `/root/.openclaw/workspace/TEMPLATES` so scaffolding remains intact regardless of where `leio-sdlc` is nested.
