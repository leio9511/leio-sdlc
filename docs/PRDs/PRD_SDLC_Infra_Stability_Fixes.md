---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: SDLC_Infra_Stability_Fixes

## 1. Context & Problem (业务背景与核心痛点)

Today's SDLC pipeline execution revealed critical infrastructure bugs that caused repeated pipeline hangs and Gateway-induced crashes:

**Bug A (ISSUE-1148): The Rogue Agent Commit Lock Deadlock.**
The git pre-commit hook exists specifically as a guardrail to **block rogue Agents (like the Manager/Main Agent) from making unauthorized manual commits** bypassing the SDLC orchestrator. It acts as a strict lock: only the SDLC pipeline (`SDLC_RUNTIME`) is authorized to commit.
However, `doctor.py --fix` currently installs a broken, minimalist placeholder hook (`exit 1`) from `TEMPLATES/scaffold/optional_hooks/`. This broken placeholder completely locks out *everybody*, including the SDLC pipeline itself. Because the placeholder lacks the `SDLC_RUNTIME` bypass logic, the moment the orchestrator tries to run, it gets permanently blocked by this overly aggressive lock, causing a complete SDLC deadlock.

**Bug B: Fake Mock E2E Tests.** 
The `scripts/e2e/mocked/` directory contains 3 "fake mock" tests that call real LLM APIs (`e2e_test_agent_driver_gemini.sh`, `e2e_test_secure_prompt.sh`, `e2e_test_reviewer_artifact_guardrail.sh`), causing preflight to hang indefinitely when external API quality is poor or rate limits are hit.

**Bug C: Orchestrator Engine Default & Actionable Error States.**
- The Auditor and Orchestrator currently default to the `openclaw` engine. They MUST default to the `gemini` engine leveraging `gemini-3.1-pro-preview` for maximum reasoning capacity.
- The `orchestrator.py` throws vague `exit(1)` errors (like `Workspace contains uncommitted state files` or `Dirty Git Workspace detected!`) without actionable self-healing steps, leaving agents stuck or hallucinating.

## 2. Requirements & User Stories (需求定义)

- **User Story 1:** As an SDLC operator, I want the `TEMPLATES` placeholder hook replaced with the correct production-grade logic that enforces the "Block Rogue Agents, Allow SDLC" lock mechanism. `doctor.py --fix` must naturally install this functional hook so the SDLC pipeline does not deadlock itself.
- **User Story 2:** As an SDLC operator, I want all mocked E2E tests to use deterministic mock drivers, ensuring preflight never hangs on external APIs.
- **User Story 3:** As an SDLC operator, I want the default execution engine changed to `gemini` system-wide.
- **User Story 4:** As a Coder/Reviewer agent, I want actionable JIT prompts injected into `exit(1)` fatal errors from the Orchestrator, so I can self-heal (e.g., using `git stash` or dynamically referencing correct paths).

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Fix the Rogue Agent Commit Lock via Single Source of Truth (SSOT) & Secure by Default
**Target files:** `scripts/doctor.py`, `deploy.sh`, `config/sdlc_config.json.template`, and `TEMPLATES/scaffold/optional_hooks/pre-commit`

We address the broken lock architecture using the SSOT pattern and a "Secure by Default" posture decoupled via the native application configuration. The complete production hook logic (including `SDLC_RUNTIME` bypass) already exists as a formally git-tracked source file at `.sdlc_hooks/pre-commit`.
1. **Remove the Poison Pill:** Delete the broken, deadlocking placeholder file `TEMPLATES/scaffold/optional_hooks/pre-commit`. We will no longer duplicate hook logic into the templates directory.
2. **Configuration Decoupling (Secure by Default):** Update the scaffold template `config/sdlc_config.json.template` to include the `"ENFORCE_GIT_LOCK": true` key. Update `scripts/doctor.py`'s `--enforce-git-lock` argument to default to this secure posture by reading the *actual* runtime configuration file (`config/sdlc_config.json`). If the actual `.json` configuration file does not exist, `doctor.py` MUST safely fallback to `True` in code. Never parse the `.template` file at runtime.
3. **Dynamic SSOT Routing:** Modify `scripts/doctor.py` so that when the lock is enabled, it copies the hook directly from `script_dir.parent / ".sdlc_hooks" / "pre-commit"`.
4. **Fix Release Packaging:** Modify `deploy.sh` to correctly sync hidden directories like `.sdlc_hooks`. Use strict isolation: `rsync -a --exclude='.git' --exclude='.gitignore' . .dist/`.
*Rationale:* This eliminates code duplication (DRY), ensures `doctor.py` natively installs the correct "Smart Lock", solves the hidden-folder deployment bug, and achieves true configuration decoupling (reading the actual JSON config, not the template) for the secure-by-default posture.

### 3.2 Fix Fake Mock E2E Tests via Explicit Dependency Injection (DI)
**Target files:**
- `scripts/e2e/mocked/e2e_test_agent_driver_gemini.sh`
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh`
- `scripts/e2e/mocked/e2e_test_reviewer_artifact_guardrail.sh`
- `scripts/agent_driver.py`

For the shell scripts, eliminate the "Path Hijacking" anti-pattern (do not put fake binaries in `$PATH`). Instead, modify the tests to utilize explicit Dependency Injection by exporting a test-specific environment variable like `SDLC_MOCK_LLM_RESPONSE`.

For `scripts/agent_driver.py`, implement the receiving end of the DI pattern: intercept the `SDLC_MOCK_LLM_RESPONSE` variable at the beginning of the `invoke_agent` execution flow. If this variable is present and the system is in a testing mode, natively short-circuit the API call and return the deterministic mock string directly, completely avoiding any real external LLM network requests and eliminating the pipeline hang risk.

### 3.3 Upgrade Default Engine & Inject Orchestrator JIT Prompts
**Target files:** `scripts/config.py` and `scripts/orchestrator.py`

1.  **`scripts/config.py`**: Change `DEFAULT_LLM_ENGINE` to `"gemini"`.
2.  **`scripts/orchestrator.py`**: Enhance the fatal error strings at key `sys.exit(1)` points with explicit JIT instructions. Keep paths deterministic using generic placeholders in the output strings, entirely avoiding Python's fragile dynamic path manipulation. The JIT prompts are intended for Agent consumption; simply instruct the Agent to locate the correct tool (e.g., "use the doctor.py script from the active SDLC runtime") and let the Agent figure out the exact resolved path autonomously.

### 3.4 Rollback Strategy
If the modifications introduce critical failures, the rollback strategy is to use `git checkout` to restore `deploy.sh`, `TEMPLATES/scaffold/optional_hooks/pre-commit`, `scripts/doctor.py`, `scripts/config.py`, `scripts/orchestrator.py`, and `scripts/agent_driver.py` to their previous commits.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** doctor --check failure shows JIT prompt
  - **Given** the workdir has a missing or broken pre-commit hook
  - **When** I run `python3 scripts/doctor.py <workdir> --check`
  - **Then** exit code is 1 AND output contains static JIT `[JIT] To fix:` instruction.

- **Scenario 2:** Black-Box Test: rogue commit is blocked
  - **Given** the workdir has the correct pre-commit hook installed via `doctor.py --fix`
  - **When** a rogue agent or user manually issues `git commit -m "test"` without SDLC_RUNTIME configuration
  - **Then** the commit process exits with code 1, actively blocking the rogue write.

- **Scenario 3:** Mocked E2E tests do not call real LLM
  - **Given** I run `./preflight.sh`
  - **Then** all tests in `scripts/e2e/mocked/` complete in under 60 seconds
  - **And** no real Gemini/openai API calls are made

- **Scenario 4:** Orchestrator Dirty State Guardrail
  - **Given** untracked files in the workspace
  - **When** I run `orchestrator.py`
  - **Then** the output contains the `git stash` JIT instruction.

- **Scenario 5:** Default Engine Verification (Black-box)
  - **Given** `LLM_DRIVER` environment variable is unset
  - **When** I trigger an SDLC execution (e.g., spawn_planner.py)
  - **Then** the process logs indicate initialization using the `gemini` driver.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **Core quality risk:** External API instability causes preflight to hang, making SDLC unusable.
- **Strategy:** All E2E tests in `mocked/` must strictly use explicit Dependency Injection (e.g., via `SDLC_MOCK_LLM_RESPONSE` or dedicated mock toggles) instead of fragile $PATH hijacking or calling real Gemini/OpenAI APIs.
- **Verification:** Run `./preflight.sh` before and after changes — it must always complete in under 60 seconds with 100% mocked isolation.

## 6. Framework Modifications (框架防篡改声明)

- `TEMPLATES/scaffold/optional_hooks/pre-commit` — authorized deletion
- `scripts/config.py` — authorized modification
- `deploy.sh` — authorized modification
- `scripts/doctor.py` — authorized modification
- `scripts/orchestrator.py` — authorized modification
- `scripts/agent_driver.py` — authorized modification
- `scripts/e2e/mocked/e2e_test_agent_driver_gemini.sh` — authorized modification
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh` — authorized modification
- `scripts/e2e/mocked/e2e_test_reviewer_artifact_guardrail.sh` — authorized modification

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)

- **v1.0**: [Initial draft — rejected by Auditor for missing template sections]
- **v1.1**: [Second draft — rejected by Auditor for Hardcoded Path Anti-Pattern and implicit blast radius in hook paths]
- **v1.2**: [Third draft — rejected by Auditor for BDD violation (Scenario 5 was white-box), Error Swallowing (|| true in deploy.sh), and hardcoded strings]
- **v1.3**: [Fourth draft — rejected by Auditor for Leaky Abstraction, String Determinism, and DRY Violation. Decided to revert to the SSOT approach and delete the redundant template hook altogether.]
- **v1.4**: [Final draft — Fixed the SSOT routing for `doctor.py` to directly use `.sdlc_hooks/pre-commit`, added string definitions for missing JIT prompts and default models.]

---

## 7. Hardcoded Content (硬编码内容)

> If this PRD does not involve any hardcoded text, write "None".

### Exact Text Replacements:

- **JIT prompt line (for scripts/doctor.py - General Failure):**
```
[JIT] To fix: Execute the `doctor.py --fix` script from the active SDLC runtime on the current <workdir>.
```

- **JIT prompt line (for scripts/orchestrator.py - Dirty Git Workspace):**
```
[JIT] To fix: Execute `git stash push -m "sdlc pre-flight stash" --include-untracked` to safely preserve state.
```

- **JIT prompt line (for scripts/orchestrator.py - Uncommitted State Files & Git Boundary):**
```
[JIT] To fix: Ensure your PRD path is within the Git repository boundaries.
If it is, use the official gateway script (commit_state.py) from the active SDLC runtime to baseline it.
```

- **LLM Engine Configuration (for scripts/config.py):**
```
DEFAULT_LLM_ENGINE = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
```

- **JSON Configuration toggle (for config/sdlc_config.json.template):**
```
"ENFORCE_GIT_LOCK": true
```

- **Mock Dependency Injection variable (for scripts/agent_driver.py and testing scripts):**
```
SDLC_MOCK_LLM_RESPONSE
```
