---
status: in_progress
---

# PR-003: Dynamic_Hints_and_Deployment_Adaptation

## 1. Objective
Make runtime-sensitive hints and deployment behavior environment-agnostic so both operator guidance and installation targets reflect the active `SDLC_RUNTIME_DIR` instead of hardcoded OpenClaw-only paths.

## 2. Target Working Set & File Placement
> **[CRITICAL INSTRUCTION TO CODER]** 
> 1. **NEW FILES:** You are STRICTLY FORBIDDEN to create new files outside of the directories listed below. No orphaned files in the root directory!
> 2. **EXISTING FILES:** You HAVE FULL FREEDOM to modify ANY existing files in the workspace necessary to make the tests pass, but you MUST prioritize the files listed here.

### 2.1 Existing Files to Modify
- [ ] `scripts/orchestrator.py`
- [ ] `scripts/doctor.py`
- [ ] `deploy.sh`
- [ ] `tests/test_080_orchestrator_dynamic_strings.py`
- [ ] `tests/test_doctor_core.py`
- [ ] `scripts/test_deploy_hardcopy.sh`

### 2.2 New Files to Create
*(None)*

## 3. Implementation Scope (实现细节)
1. Update runtime-facing error and JIT outputs in `scripts/orchestrator.py` so they reference the active runtime directory instead of a hardcoded `~/.openclaw/skills` path.
   - Wherever the PRD baseline/commit-state guidance is emitted, use the exact Section 7 `runtime_hint_template` with the resolved absolute runtime dir.
2. Update `scripts/doctor.py` so its compliance guidance is runtime-aware:
   - Any message that points operators to the installed SDLC location must derive that path from `config.SDLC_RUNTIME_DIR`.
   - Keep its failure semantics intact while removing hardcoded path assumptions.
3. Update `deploy.sh` so the deployment target respects `SDLC_RUNTIME_DIR`:
   - If `SDLC_RUNTIME_DIR` is set, use that as the skills/install root.
   - Preserve current release backup behavior, atomic swap behavior, and fallback behavior when the variable is absent.
4. Do not widen scope into unrelated notifier integration here; this PR is specifically about operator-facing runtime paths and install destinations.

## 4. TDD Blueprint & Acceptance Criteria (QA 测试蓝图)
> **[Instruction to Coder]** Implement these test cases exactly in the test files specified in section 2. You must ensure the CI preflight script passes before considering this task done.
- [ ] Test Case 1: `test_orchestrator_dynamic_strings` in `tests/test_080_orchestrator_dynamic_strings.py` (Expected: the uncommitted-PRD failure message contains the exact runtime-aware `commit_state.py` path rooted at the active `SDLC_RUNTIME_DIR`).
- [ ] Test Case 2: `test_doctor_check_reports_runtime_aware_fix_path` in `tests/test_doctor_core.py` (Expected: doctor check-mode output references the active runtime path instead of a hardcoded OpenClaw skills directory).
- [ ] Test Case 3: `test_deploy_sh_respects_runtime_dir` in `scripts/test_deploy_hardcopy.sh` (Expected: setting `SDLC_RUNTIME_DIR` redirects deployment into the custom runtime root while preserving a green hard-copy deployment flow).