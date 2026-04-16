---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: SDLC_Infra_Stability_Fixes

## 1. Context & Problem (业务背景与核心痛点)

Today's SDLC pipeline execution revealed two critical infrastructure bugs that caused repeated pipeline hangs, Gateway-induced crashes, and overall instability:

**Bug A (ISSUE-1148):** `doctor.py --fix` installs a placeholder pre-commit hook from the `TEMPLATES/` directory instead of the production-grade hook from `scripts/.sdlc_hooks/`. The placeholder hook does not support `SDLC_ORCHESTRATOR_RUNNING`, creating a security gate deadlock where SDLC blocks itself.

**Bug B:** The `scripts/e2e/mocked/` directory contains 3 "fake mock" tests that call real LLM APIs, causing preflight to hang indefinitely when API quality is poor:
- `e2e_test_agent_driver_gemini.sh` — directly invokes real Gemini API
- `e2e_test_secure_prompt.sh` — spawn_planner.py triggers real LLM call
- `e2e_test_reviewer_artifact_guardrail.sh` — copies real openclaw binary as fake gemini

These tests are in the `mocked/` directory, implying they should be safe to run in preflight, but they actually call external APIs and can hang.

## 2. Requirements & User Stories (需求定义)

- **User Story 1:** As an SDLC operator, I want `doctor.py --fix` to install the correct production-grade pre-commit hook so that the security gate does not block the SDLC pipeline itself.
- **User Story 2:** As an SDLC operator, I want all mocked E2E tests to use mock LLM drivers, so that preflight never hangs due to external API failures.
- **User Story 3:** As a Coder/Reviewer agent, I want actionable JIT prompts when `doctor --check` fails, so I can self-heal without human intervention.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Fix doctor.py Hook Installation
**Target file:** `scripts/doctor.py`

In the `apply_overlay()` function, the code currently copies from `TEMPLATES/scaffold/optional_hooks/pre-commit` (a placeholder that always exits 1). We must change it to copy from `scripts/.sdlc_hooks/pre-commit` (the production hook that checks `SDLC_ORCHESTRATOR_RUNNING`).

### 3.2 Fix Fake Mock E2E Tests
**Target files:**
- `scripts/e2e/mocked/e2e_test_agent_driver_gemini.sh`
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh`
- `scripts/e2e/mocked/e2e_test_reviewer_artifact_guardrail.sh`

For each file, ensure the LLM driver used is a true mock. The pattern used by other well-behaved mocked tests is:
- Set `LLM_DRIVER=openclaw`
- Create a mock binary in `$PATH` that returns deterministic output
- Do NOT call real Gemini/openai APIs

### 3.3 Add JIT Prompts to doctor --check
**Target file:** `scripts/doctor.py`

When `check_only=True` and issues are found, append a machine-readable actionable line to the `[FATAL]` message:
```
[JIT] To fix: python3 ~/.openclaw/skills/leio-sdlc/scripts/doctor.py <workdir> --fix
```

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** doctor --check failure shows JIT prompt
  - **Given** the workdir has a missing or broken pre-commit hook
  - **When** I run `python3 scripts/doctor.py <workdir> --check`
  - **Then** exit code is 1 AND output contains `[JIT] To fix: python3`

- **Scenario 2:** doctor --fix installs correct hook
  - **Given** the workdir has an incorrect pre-commit hook
  - **When** I run `python3 scripts/doctor.py <workdir> --fix`
  - **Then** `.git/hooks/pre-commit` contains `SDLC_ORCHESTRATOR_RUNNING`

- **Scenario 3:** Mocked E2E tests do not call real LLM
  - **Given** I run `./preflight.sh`
  - **Then** all tests in `scripts/e2e/mocked/` complete in under 60 seconds
  - **And** no real Gemini/openai API calls are made

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **Core quality risk:** External API instability causes preflight to hang, making SDLC unusable
- **Strategy:** All E2E tests in `mocked/` must use mock drivers only. Use the pattern from `e2e_test_1093_global_dir_decoupling.sh` as the reference implementation (mock binary in `$PATH` that exits 0).
- **Verification:** Run `./preflight.sh` before and after changes — it must always complete in under 60 seconds

## 6. Framework Modifications (框架防篡改声明)

- `scripts/doctor.py` — authorized modification
- `scripts/e2e/mocked/e2e_test_agent_driver_gemini.sh` — authorized modification
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh` — authorized modification
- `scripts/e2e/mocked/e2e_test_reviewer_artifact_guardrail.sh` — authorized modification

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)

- **v1.0**: [Initial draft — rejected by Auditor for missing template sections]

---

## 7. Hardcoded Content (硬编码内容)

> If this PRD does not involve any hardcoded text, write "None".

### Exact Text Replacements:

- **JIT prompt line (for scripts/doctor.py):**
```
[JIT] To fix: python3 ~/.openclaw/skills/leio-sdlc/scripts/doctor.py <workdir> --fix
```
