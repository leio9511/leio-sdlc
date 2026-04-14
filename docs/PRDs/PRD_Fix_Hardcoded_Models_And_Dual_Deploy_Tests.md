---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix_Hardcoded_Models_And_Dual_Deploy_Tests

## 1. Context & Problem (业务背景与核心痛点)
1. In recent changes (PR-001, PR-002), the dual compatibility deployment logic was added to the main `deploy.sh` and `pm-skill/deploy.sh`. However, the comprehensive integration tests ensuring `deploy.sh` correctly copies `.dist/scripts/` to `.openclaw/skills/` without dropping `.py` or `.sh` files were missing or incomplete.
2. The `SDLC_MODEL` defaults in `scripts/agent_driver.py` and test mocks in `tests/test_gemini_agent_driver.py` were improperly hardcoded in the driver logic itself. This violates the Configuration Externalization anti-pattern. 
3. **Workspace Pollution**: The `.tmp` directory for JIT prompt injection is incorrectly placed inside the `project_root` (e.g., `leio-sdlc/.tmp`), which pollutes the local workspace. It should be placed securely under the `global_dir` (e.g., `~/.openclaw/workspace/.tmp`).
4. **Tool Use Hallucination (Gemini CLI)**: The `gemini` CLI driver branch injects massive prompts via the `-p` direct argument. This causes headless `gemini` to treat the prompt as a text-completion task rather than an Agentic Tool Loop.
5. **Session Management & Race Conditions**: The `gemini` CLI auto-generates internal UUIDs for sessions. If we naively poll for the "latest" session to resume a stateful Coder agent, concurrent SDLC runs will cause race conditions. A unified "Session Translation Layer" is required so SDLC session keys map safely to driver-specific keys without timing vulnerabilities.

## 2. Requirements & User Stories (需求定义)
1. **Extract Magic Strings to Config Layer**: Create `scripts/config.py`.
2. **Global Temp Directory Fix**: Resolve `.tmp` securely under `~/.openclaw/workspace/.tmp`.
3. **File Indirection for Gemini CLI**: Use `-p secure_msg` pointing to the temp file.
4. **Unified Session Translation Layer**: Implement a JSON mapping layer in `agent_driver.py` (`~/.openclaw/workspace/.tmp/session_map.json`). 
   - `openclaw` driver maps the SDLC key to itself.
   - `gemini` driver captures its generated UUID and maps the SDLC key to this UUID.
   - Provide absolute anti-race-condition capture logic for Gemini UUIDs.
5. **Fix Missing Dual Deploy Tests**: Implement bash-based sandbox test cases.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Configuration Externalization (配置隔离)**: 
  - Create `scripts/config.py` with `DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"`.
- **Global Temp Directory**: `temp_dir = os.path.expanduser("~/.openclaw/workspace/.tmp")`.
- **Unified Session Translation Map**:
  - Maintain a stateful dictionary loaded/saved from `os.path.join(temp_dir, "session_map.json")`.
  - **Resume Logic**: Before invoking the CLI, lookup `sdlc_session_key`. If a driver-specific key exists, use it (`--session-id` for openclaw, `-r` for gemini).
  - **Creation & Anti-Race Capture**: If no key exists, run the new session. For `gemini`, post-execution, run `gemini --list-sessions`. Safely parse the output by searching for the unique `sdlc_prompt_{sdlc_session_key}` substring in the history list to extract the exact UUID (e.g., `\[([a-f0-9\-]{36})\]`). Because the temp filename is cryptographically unique per session, this mathematically guarantees no race conditions. Save the mapping.
- **Sandbox Testing for Bash**: Dry-run deployment scripts using isolated temporary directories.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** Temp prompt files are created in the global workspace.
  - **Given** an SDLC run.
  - **Then** the file is located in `~/.openclaw/workspace/.tmp`.
- **Scenario 2:** Gemini CLI behaves agentically via File Indirection.
  - **Then** the CLI command uses `-p "Read your complete task instructions from ..."`.
- **Scenario 3:** Session mapping eliminates race conditions.
  - **Given** a stateful Coder session run via `gemini`.
  - **When** the execution completes and mapping is saved.
  - **Then** the correct UUID is extracted by matching the unique prompt filename, and subsequent calls resume correctly using `-r UUID`.
- **Scenario 4:** Dual deployment is fully tested.
  - **Then** integration tests pass cleanly in isolated directories.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Python unit tests in `tests/test_gemini_agent_driver.py` must mock the mapping dictionary and `gemini --list-sessions` output to verify robust regex parsing and fallback.
- **Sandbox Integration Testing**: Bash scripts simulate isolated deployments.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/config.py` (New file)
- `scripts/agent_driver.py`
- `tests/test_gemini_agent_driver.py`
- `tests/test_034_dual_deploy.sh`

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:
- **For `scripts/config.py` (Define system constants)**:
```python
# System-wide configuration constants
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
```

- **For `scripts/agent_driver.py` (File Indirection prompt wrapper)**:
```python
secure_msg = f"Read your complete task instructions from {path}. Do not modify this file."
```