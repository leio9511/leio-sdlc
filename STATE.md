# STATE.md - leio-sdlc Development State (Kanban)

- **Project**: leio-sdlc (Automated SDLC Orchestrator)
- **Current Version**: 0.6.0
- **Status**: [SDLC Hardening] - Implementing native notifications, fail-fast git hygiene, and deterministic state tracking.
- **Active Branch**: `master`

## 🏆 Recently Completed
- [x] **[ISSUE-1018] PRD-1018: Enforce Channel Parameter**: Orchestrator now strictly requires --channel and fails-fast on missing notification target. (v0.5.5)
- [x] **[ISSUE-1015] PRD-1015: Hard-Copy Deployment Strategy**: Replaced symlink Blue/Green deploy with atomic directory swapping for AgentSkills. (v0.5.4)
- [x] **[ISSUE-1019] PRD-1019: Clean Workspace Escalation**: Git reset --hard and clean -fd on State 5 Tier 1 recovery. (v0.5.3)
- [x] **[ISSUE-1010] PRD-1010: Orchestrator Self-Explanation**: Enforced strict CLI parameters and implemented the 5 Tool-as-Prompt handoff exit points. (v0.5.2)
- [x] **[ISSUE-1011 & 1012] PRD-1011: Global Lock & Deadlock Fix**: Implemented fcntl global singleton lock and resolved the reviewer guardrail deadlock. (v0.5.1)
- [x] **[ISSUE-067] Migrate SDLC to Gemini ACP**: Coder now uses persistent sandboxed ACP sessions via openclaw agent CLI.
- [x] **[ISSUE-054] State 0: PRD Ingestion & Auto-Slicing**: Orchestrator can now accept a raw PRD and automatically trigger the Planner.
- [x] **[ISSUE-1010] PRD-1010: Orchestrator Self-Explanation**: Enforced strict CLI parameters and implemented the 5 Tool-as-Prompt handoff exit points. (v0.5.2)
- [x] **[ISSUE-1007] PRD-079: SDLC Slack Notifications & Git Hygiene**: Native channel broadcast and Semantic Commit Enforcement. (v0.4.0)
- [x] **[ISSUE-077] CLI Command Mismatch for ACP**: Replaced internal Tool APIs with valid OpenClaw CLI commands (`openclaw agent --session-id`).
- [x] **[ISSUE-074] Information Silo & Dependency Injection**: Orchestrator now serves as Single Source of Truth for Review Report artifact paths.
- [x] **[ISSUE-075] Robust Git State Management**: Implemented `safe_git_checkout` and automatic explicit state commits, eliminating dirty-tree branch crashes.
- [x] **[ISSUE-064] Anti-Reward Hacking Isolation (PRD-064)**: Refactored `orchestrator.py` to use `__file__` absolute paths (`RUNTIME_DIR`), physically preventing the Coder from hijacking the testing framework or Reviewer via relative path execution from the workspace. (v0.2.6)
- [x] **[ISSUE-063] Planner Micro-Slicing & Test Fixes**: Resolves issue tracker/artifact hang bugs. (v0.2.5)
- [x] **[ISSUE-057] PR Directory Isolation by PRD**: Micro-PRs are now physically isolated in `docs/PRs/<PRD_Name>/`. Engine processes isolated queues flawlessly.

## 🚀 Active Milestones & Next in Queue

- **[ISSUE-1008] PRD-080: leio-manager AgentSkill**: Deterministic artifact lifecycle management CLI to replace LLM state tracking. [TODO]
- **M3: End-to-End Orchestrator Autonomy (State 0 to State 6)** [IN PROGRESS]
  - [ ] **[ISSUE-055] Global Control Tower**: A dashboard/snapshot tool to track the engine's real-time state.

## 📜 History
- **2026-03-25**: Massive issue board cleanup. Synced stale resolved issues (011, 036, 037, 066, 1003, 1005, 1007, 1010) to closed state.
- **2026-03-22**: Handbook rewritten. Issue System declared as SSOT.
- **2026-03-17**: Engine upgraded to v0.2.6. Reward Hacking & Prompt Injection physically blocked via absolute path isolation.
- **2026-03-17**: Engine stabilized (v0.2.3). Autonomous loop (Coder -> Reviewer -> Merge -> Teardown) successfully executed without human intervention for PRD-057.
- **2026-03-13**: Project promoted to workspace root. SDLC for SDLC initiated (v0.0.1).
