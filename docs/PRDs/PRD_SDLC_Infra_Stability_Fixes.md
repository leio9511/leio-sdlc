---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: SDLC_Infra_Stability_Fixes

## 1. Context & Problem

Today's SDLC pipeline execution revealed two critical infrastructure bugs that caused repeated pipeline hangs, repeated Gateway-induced crashes, and overall instability:

**Bug A (ISSUE-1148):** `doctor.py --fix` installs an incorrect placeholder pre-commit hook, creating a security gate deadlock where SDLC blocks itself.

**Bug B:** The `scripts/e2e/mocked/` directory contains "fake mock" tests that call real LLM APIs, causing preflight to hang indefinitely when API quality is poor.

## 2. Requirements & User Stories

- **User Story 1:** As an SDLC operator, I want `doctor.py --fix` to install the correct production-grade pre-commit hook so that the security gate does not block the SDLC pipeline itself.
- **User Story 2:** As an SDLC operator, I want all mocked E2E tests to use mock LLM drivers, so that preflight never hangs due to external API failures.
- **User Story 3:** As a Coder/Reviewer agent, I want actionable JIT prompts when `doctor --check` fails, so I can self-heal without human intervention.

## 3. Target Files & Scope

### File A: Fix doctor.py hook installation
- **File:** `scripts/doctor.py`
- **Change:** In `apply_overlay()`, when copying `optional_hooks/pre-commit`, use the production hook from `scripts/.sdlc_hooks/pre-commit` (the one that respects `SDLC_ORCHESTRATOR_RUNNING`) instead of the placeholder from `TEMPLATES/scaffold/optional_hooks/pre-commit`.

### File B: Fix fake mock E2E tests
- **Files:**
  1. `scripts/e2e/mocked/e2e_test_agent_driver_gemini.sh` — calls real Gemini API
  2. `scripts/e2e/mocked/e2e_test_secure_prompt.sh` — spawn_planner.py triggers real LLM
  3. `scripts/e2e/mocked/e2e_test_reviewer_artifact_guardrail.sh` — copies real openclaw as fake gemini
- **Change:** For each file, ensure the LLM driver used is a true mock (e.g., set `LLM_DRIVER=openclaw` and mock the binary to return a deterministic response). Add `|| true` where appropriate so failures do not block preflight.

### File C: Add JIT prompts to doctor --check failure
- **File:** `scripts/doctor.py`
- **Change:** When `check_only=True` and issues are found, in addition to the `[FATAL]` message, append a machine-readable actionable line:
  ```
  [JIT] To fix: python3 ~/.openclaw/skills/leio-sdlc/scripts/doctor.py <workdir> --fix
  ```

## 4. Acceptance Criteria

- `python3 scripts/doctor.py /root/projects/leio-sdlc --check` returns exit code 1 AND prints `[JIT] To fix: python3 ...`
- `python3 scripts/doctor.py /root/projects/leio-sdlc --fix` installs the correct production hook (check via `grep -c "SDLC_ORCHESTRATOR_RUNNING" .git/hooks/pre-commit`)
- All `scripts/e2e/mocked/*.sh` tests pass with `RUN_LIVE_LLM=0` without hanging
- `./preflight.sh` completes in under 60 seconds without any real LLM API calls

## 5. Test Strategy

- Run `./preflight.sh` before and after changes — should always complete
- Verify `.git/hooks/pre-commit` contains `SDLC_ORCHESTRATOR_RUNNING`
- Verify no `scripts/e2e/mocked/*.sh` exports `LLM_DRIVER=gemini` without a mock fallback

## 6. Scope Constraints

- Do NOT change any production hook logic or security behavior
- Do NOT modify test assertions — only ensure mock tests use mock drivers
- This is an infrastructure stability fix, not a feature change
