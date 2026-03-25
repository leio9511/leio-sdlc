Here is the **Architectural Audit Report v5** based on a devastatingly critical analysis of PRD-1022 v2 against the current orchestrator codebase and the Polyrepo migration plan. I have also written this report to `/root/.openclaw/workspace/projects/leio-sdlc/Architectural_Audit_Report_v5.md` for your records.

***

# Architectural Audit Report v5: PRD-1022 (Polyrepo Compatibility)

## Executive Summary
The proposed "Hub & Spoke Polyrepo" migration plan (PRD-1022 v2) is fundamentally sound in theory, but the **current implementation in the `orchestrator.py` and spawn scripts is disastrously misaligned with the PRD**. The orchestrator codebase actively violates the PRD's directives, failing to provide the requested concurrency safety, and introduces a critical OS-level crash vulnerability regarding command-line argument limits.

If this code is deployed in a polyrepo environment, it will fail immediately. 

---

## 1. Context Switching & Git Boundaries (Critical Failure)

**PRD Directive:** `"os.chdir(args.workdir) MUST be executed immediately after argparse resolution. ALL git operations... MUST happen after switching to the target workdir."`

**Code Reality:** 
In `orchestrator.py`, the following actions occur **BEFORE** `argparse.ArgumentParser().parse_args()` and before `os.chdir(workdir)`:
1. `git branch --show-current` (Line 55)
2. `git status --porcelain` (Line 72)

**Impact:** The orchestrator checks the branch and dirty status of the **global workspace** (`/root/.openclaw/workspace`), NOT the target sub-repo. 
- If the global workspace is on `main` instead of `master`, or has untracked files, the pipeline will `sys.exit(1)` and refuse to run for a perfectly clean, properly branched sub-repo.
- The Git Boundary Enforcement checking for a `.git` folder inside the `workdir` is completely missing from `orchestrator.py`.

---

## 2. Per-Repo Granular Locking (Critical Failure)

**PRD Directive:** `"Replace the hardcoded global .sdlc_run.lock with a strict per-repository lock file: os.path.join(args.workdir, '.sdlc_repo.lock')."`

**Code Reality:**
In `orchestrator.py` (Line 61), the script still hardcodes the global lock:
```python
lock_fd = os.open(".sdlc_run.lock", os.O_CREAT | os.O_RDWR)
```
And it does this *before* it even knows what the `workdir` is. 

**Impact:** Concurrent execution across different polyrepos is physically blocked. You cannot run an SDLC pipeline on `projects/AMS` and `projects/ClawOS` simultaneously. The orchestrator is still behaving as a global singleton locking out the entire OS process.

---

## 3. "Memory-Based PRD Injection" & OS Limits (Catastrophic Vulnerability)

**PRD Directive:** `"The orchestrator MUST read the PRD file into memory and pass its content directly via prompt injection to spawn_planner.py and spawn_coder.py."`

**Code Reality:**
`spawn_planner.py` and `spawn_coder.py` correctly read the files into memory, construct a massive `task_string` (containing the playbook, the PRD, the template, and the PR contract), and then execute it via CLI flags:
```python
cmd = ["openclaw", "agent", "--session-id", session_id, "-m", task_string]
subprocess.run(cmd)
```

**Impact:** **`OSError: [Errno 7] Argument list too long` (E2BIG).**
Passing potentially 50KB+ of markdown text as a command-line argument (`argv`) to a subprocess is a severe anti-pattern in Linux. The `MAX_ARG_STRLEN` or stack limits will truncate or crash the invocation for medium-to-large PRDs. Memory-based injection is feasible, but **not** via `sys.argv`.
*Mitigation:* The spawned agent must read the prompt via standard input (`stdin`) piping, or the spawn scripts should write the transient composite prompt to a secure temporary file (e.g., `/tmp/sdlc_prompt_X.txt`) and pass the file path to the CLI, rather than injecting gigabytes of text directly into `-m`.

---

## 4. Pathing and Template Vulnerabilities (High Risk)

**A. Playbook Paths:**
In `spawn_coder.py` (Line 89) and `spawn_planner.py`, the playbook is resolved via:
`os.path.join(SDLC_DIR, "..", "playbooks", "coder_playbook.md")`
In a Polyrepo architecture where `leio-sdlc` is moved to `projects/leio-sdlc`, `..` resolves to `projects/`, NOT the global workspace. The orchestrator will silently fail to find the playbooks.

**B. PR Template Paths:**
In `spawn_planner.py` (Line 61):
`os.path.join(workdir, "TEMPLATES", "PR_Contract.md.template")`
This assumes the `TEMPLATES` folder is copied into every individual sub-repo `workdir`. The Polyrepo plan implies global templates remain in the global workspace. If `TEMPLATES` is not initialized inside the target sub-repo, it falls back to a hardcoded string and severs the central template inheritance.

**C. Scaffolding Ignorance:**
In `spawn_planner.py`, it copies `.gitignore` from `os.path.join(SDLC_DIR, "..", ".gitignore")`. If executed in a sub-repo, it attempts to pull the `.gitignore` from `projects/.gitignore` rather than the global `.gitignore` blueprint.

---

## Conclusion & Next Actions
PRD-1022 v2 accurately identifies the V1 flaws, but the current source code completely ignores the PRD instructions. It is not safe to roll out.

**Required Actions for the Coder:**
1. **Rearrange Orchestrator Boot Sequence:** Move `argparse` to the absolute top of `orchestrator.py` `main()`.
2. **Defer Git Checks:** Move the OS Lock (`fcntl`), `git branch`, and `git status` checks to happen *strictly after* `os.chdir(workdir)`.
3. **Fix the Lock:** Change the `.sdlc_run.lock` to `.sdlc_repo.lock` applied within `args.workdir`.
4. **Solve E2BIG Vulnerability:** Refactor the `openclaw agent -m` invocation in the spawners to use `stdin` or temporary file pointers instead of CLI arguments.
5. **Absolute Pathing Context:** Pass a `--global-workspace` or `--template-dir` absolute path argument down from `orchestrator.py` to the spawners so they can reliably locate global playbooks and templates regardless of repo placement.
