# Architectural Audit Report v4: Hub & Spoke Polyrepo Migration (PRD-1022)

**Status:** REJECTED / REVISION REQUIRED
**Auditor:** Independent Senior Architecture Auditor
**Target Documents:** `polyrepo_plan.md`, `PRD_1022_Polyrepo_Compatibility.md`, Orchestrator Source Code.

## Executive Summary
While PRD-1022 correctly identifies that the current monolithic `orchestrator.py` evaluates Git state and OS locks globally *before* parsing arguments, the proposed solutions in the PRD introduce catastrophic race conditions, state corruption bugs, and portability violations. The implementation plan as written in PRD-1022 is fundamentally flawed and will cause the Polyrepo CI/CD pipeline to self-destruct if executed.

---

## 🛑 SEVERITY 1: CATASTROPHIC FLAWS

### 1. The Git Working Tree Concurrency Wipeout (Locking Strategy)
**The PRD Proposal:** Replace global lock with a PRD-specific lock file (e.g., `.sdlc_run_<PRD_BASENAME>.lock`) inside the `--workdir`.
**The Vulnerability:** 
This is a fatal misunderstanding of how Git working trees operate. If a user invokes the orchestrator twice on the *same target sub-repo* with *two different PRDs*, PRD-1022 allows both processes to acquire different lock files and run concurrently. 
Because Git only supports one active working tree per `.git` folder, Process A will execute `git reset --hard` and `git clean -fd` (State 6 / Escalation Tier 1) while Process B's Coder is actively writing code or staging commits. 
**Impact:** Total data loss of agent-generated code, git index corruption, and infinite failure loops. 
**Correction:** The lock **MUST BE STRICTLY PER-REPOSITORY**, regardless of the PRD name. It should be `<workdir>/.sdlc_repo.lock`. You cannot safely parallelize operations within the same physical `.git` working tree.

### 2. The "Dirty Workspace" Infinite Loop (PRD Internalization)
**The PRD Proposal:** Automatically copy the global PRD from `/root/../docs/PRDs/` into `<workdir>/docs/PRDs/` so agents can read it locally.
**The Vulnerability:**
Currently, `orchestrator.py` enforces a strict rule: the git workspace must be clean. If you blindly copy a PRD into the target `workdir`, you have just introduced an untracked file into the Git repository. 
When `spawn_coder.py` finishes, the orchestrator evaluates `git status --porcelain`. It will see the untracked `docs/PRDs/PRD_xxx.md` file, assume the Coder left artifacts behind, throw a "Dirty workspace detected after Coder" system alert, and respawn the Coder endlessly in a retry loop.
Additionally, silently copying files risks overwriting existing sub-repo data without consent.
**Correction:** Do not copy the PRD into the target repository's file system unless you are also going to `git add` and `git commit` it dynamically, which pollutes the target repo's git history. Instead, the orchestrator should read the global PRD into memory and pass its *contents* via prompt injection to the sub-agents, or read from the absolute path directly since the orchestrator runs outside the agent's jail.

### 3. Hardcoded Anti-Portability (Template Pathing)
**The PRD Proposal:** Hardcode the template path to the absolute global workspace: `/root/.openclaw/workspace/TEMPLATES`.
**The Vulnerability:**
This violates the core tenet of Polyrepo isolation and general software portability. If the project is cloned by a different developer in `/home/alice/workspace/` or executed inside an ephemeral CI container under `/build/`, the orchestrator will instantly crash.
**Correction:** Templates belong to the *orchestrator toolchain*, not the target project. Resolve `TEMPLATES` dynamically relative to the `spawn_planner.py` script location (e.g., `os.path.join(os.path.dirname(__file__), "../TEMPLATES")`), or strictly mandate the `--template-dir` argument. Never hardcode `/root/`.

---

## ⚠️ SEVERITY 2: ARCHITECTURAL EDGE CASES MISSED

1. **Pre-Argparse Execution Traps in `orchestrator.py`:**
   PRD-1022 mentions moving `os.chdir(args.workdir)` *after* `argparse`. However, the current code executes `subprocess.run(["git", "branch"])`, file locking, AND `git status --porcelain` completely above the `argparse` block. If `orchestrator.py` is invoked from a directory that isn't a git repo, `git branch` will throw a fatal error before `argparse` even has a chance to read `--workdir`. The PRD must explicitly specify that *all* Git validations must be deferred until after `os.chdir(workdir)`.

2. **The Branch Check Paradox:**
   The code requires the orchestrator to start from the `master` branch. In a polyrepo world, the target repo might use `main` as the default branch, or start empty. The hardcoded check for exactly `"master"` will break initialization on modern Git repositories that default to `main`.

## AUDIT VERDICT
**DO NOT IMPLEMENT PRD-1022 AS WRITTEN.** The current plan will destroy target repositories via concurrent checkout conflicts and infinite dirty-workspace loops. Revise PRD-1022 to enforce Per-Repo Locking, Memory-based/Contextual PRD passing (no copying), and Relative Path Template resolution.
