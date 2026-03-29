---
Affected_Projects: [leio-sdlc]
---

# PRD: Polyrepo Compatibility (v8)

## 1. Context & Problem Definition (核心问题与前因后果)
V7 failed because global mutexes were improperly keyed by PRD_Name instead of the target project, bypassing mutual exclusion on the repos. Furthermore, an autonomous '--cleanup' without liveness checks would maliciously destroy healthy, actively running pipelines.

## 2. Requirements (需求说明)
1. **Global Run State Directory**: Refactor `spawn_planner.py` and `create_pr_contract.py` to save generated PR slices into a Git-ignored global directory: `/root/.openclaw/workspace/.sdlc_runs/<PRD_Name>/`.
2. **Multi-Repo Directory Tree**: Inside `.sdlc_runs/<PRD_Name>/`, group PR slices by target project (e.g., `.sdlc_runs/PRD_1024/leio-sdlc/PR_001.md`).
3. **Stateless File I/O Tracking**: `orchestrator.py`'s `set_pr_status()` must update PR status via pure File I/O. Delete all legacy Git add/commit commands in `orchestrator.py` used for tracking PR slices.
4. **Nomadic Orchestration**: `orchestrator.py` iterates through project folders in `.sdlc_runs/<PRD_Name>/`, resolving the `effective_workdir` and executing all sub-agents against this target repo.
5. **Resource-Centric Locking with Liveness (The V8 Fix)**: Retain locks keyed by the resource: `/root/.openclaw/workspace/locks/<ProjectName>.lock`. When the Orchestrator acquires the lock, it MUST write a JSON payload into the lock file containing its own Process ID (`PID`) and the `active_workdir` (absolute path to the target repository).
6. **Autonomous Forensic Cleanup with Liveness Check**: The `--cleanup` command takes NO arguments. It scans all `*.lock` files in the global locks directory. For each lock, it reads the JSON payload to extract the PID and `active_workdir`. It MUST perform a Liveness Check (e.g., `os.kill(pid, 0)`). If the PID is still alive, the cleanup script skips the lock. If the PID is dead, it navigates to the `active_workdir`, executes the forensic quarantine protocol, and deletes the stale lock file.
7. **Test Suite Blast Radius**: Update all `scripts/test_*.sh` integration tests to mock and assert against the new `.sdlc_runs` path and JSON lock logic.

## 3. Architecture (架构设计)
**K8s-style Stateless Runner + Global State Dir + Resource-Centric Liveness Locks:**
The pipeline separates state from execution. By moving PR slices to a global `.sdlc_runs/` directory and grouping them by project, the `orchestrator.py` can act nomadically, iterating over targets. Concurrency is strictly controlled by resource-centric locks (`locks/<ProjectName>.lock`) containing a JSON payload (PID and active_workdir) for robust liveness checks, preventing the malicious destruction of healthy pipelines during cleanup. File I/O replaces Git commits for state tracking.

## 4. Acceptance Criteria (验收标准)
- [ ] Locks are keyed by ProjectName and contain JSON payloads with PID and active_workdir.
- [ ] Cleanup autonomously scans locks and uses Liveness Checks to quarantine ONLY crashed pipelines.

## 5. Framework Modifications (框架修改声明)
- `scripts/spawn_planner.py`
- `scripts/orchestrator.py`
- `scripts/get_next_pr.py`
- `scripts/create_pr_contract.py`
- `scripts/test_*.sh`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v8**: Drafted to resolve V7 global mutex locking issues and destructive cleanup behaviors.
