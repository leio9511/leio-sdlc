---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix_Hardcoded_Models_And_Dual_Deploy_Tests

## 1. Context & Problem (业务背景与核心痛点)
1. In recent changes (PR-001, PR-002), the dual compatibility deployment logic was added to the main `deploy.sh` and `pm-skill/deploy.sh`. However, the comprehensive integration tests ensuring `deploy.sh` correctly copies `.dist/scripts/` to `.openclaw/skills/` without dropping `.py` or `.sh` files were missing or incomplete.
2. The `SDLC_MODEL` defaults and test mocks in `scripts/agent_driver.py` and `tests/test_gemini_agent_driver.py` were improperly hardcoded to other models in recent edits. The system standard requires the model to be `gemini-3.1-pro-preview`.

## 2. Requirements & User Stories (需求定义)
1. **Fix Missing Dual Deploy Tests**: Implement bash-based test cases (e.g., `tests/test_034_dual_deploy.sh` or update existing tests) to verify the dual deployment logic in both the main `leio-sdlc/deploy.sh` and `skills/pm-skill/deploy.sh`.
2. **Update Hardcoded Model Names**: Correct `SDLC_MODEL` default fallback value to `gemini-3.1-pro-preview` inside `scripts/agent_driver.py` where the gemini LLM driver is invoked. Update `tests/test_gemini_agent_driver.py` to assert against `gemini-3.1-pro-preview`.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Model Name Fix**: Modify `os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL", "gemini-3.1-pro-preview")` in `scripts/agent_driver.py`.
- **Test Alignment**: Update the assertions in `tests/test_gemini_agent_driver.py` to check for `gemini-3.1-pro-preview`.
- **Deploy Tests**: Create or update the relevant bash test scripts inside `tests/` directory to dry-run the deployment scripts (`deploy.sh`) by copying to a temporary `.dist/` and fake target directory, asserting that the target directory contains the expected `scripts/*.py` and `deploy.sh` files.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** The default model for Gemini is correctly set.
  - **Given** no `SDLC_MODEL` or `TEST_MODEL` environment variables are set.
  - **When** `agent_driver.py` invokes the gemini driver.
  - **Then** the `--model` argument passed to the CLI is exactly `gemini-3.1-pro-preview`.

- **Scenario 2:** Dual deployment is fully tested.
  - **Given** the `leio-sdlc` deployment scripts (`deploy.sh` and `skills/pm-skill/deploy.sh`).
  - **When** the new dual deploy tests are executed.
  - **Then** they pass successfully, proving that scripts are copied successfully to both workspace and system skill directories without pathing errors.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Python unit tests in `tests/test_gemini_agent_driver.py` must mock the environment to test model fallback behavior.
- **Integration Testing**: Bash scripts must simulate the deployment environment (using temporary directories) to ensure `deploy.sh` operates correctly without side effects.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `tests/test_gemini_agent_driver.py`
- `tests/test_032_pm_skill.sh` (or new test script like `test_034_dual_deploy.sh`)

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:
- **Model Name**: 
  `gemini-3.1-pro-preview`
