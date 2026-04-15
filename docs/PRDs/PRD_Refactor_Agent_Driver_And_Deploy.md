---
Affected_Projects: [leio-sdlc]
---

# PRD: Refactor_Agent_Driver_And_Deploy

## 1. Context & Problem (业务背景与核心痛点)
Following the implementation of dual deployment tests and Gemini CLI session mapping, several enhancements are required to improve operability, isolation, and automation (tracked in ISSUE-1128):
1. **JIT Prompt Isolation (Sandbox)**: The temporary prompt file (`sdlc_prompt_*.txt`) is currently stored in the global `~/.openclaw/workspace/.tmp`. This shared directory complicates garbage collection and risks cross-SDLC run interference. It should be isolated within each SDLC run directory.
2. **Headless Deploy Automation**: Deployment scripts (`deploy.sh`, `kit-deploy.sh`) stall when the `gemini` CLI prompts for interactive confirmation (`Do you want to continue? [Y/n]`) during `gemini skills link`.
3. **Implicit Engine & Model Configuration**: Relying solely on environment variables (`LLM_DRIVER` and `SDLC_MODEL`) hides the execution context from CLI history. Explicit CLI arguments are needed for `orchestrator.py` and its subordinate `spawn_*.py` scripts.

## 2. Requirements & User Stories (需求定义)
1. **Consolidate Defaults via SSOT**: The `scripts/config.py` file remains as the Single Source of Truth (SSOT) for system-wide defaults. All entrypoint scripts (`orchestrator.py` and manually run `spawn_*.py`) will import this constant to set their CLI argument defaults.
2. **Per-Run JIT Prompt Isolation**: Refactor `agent_driver.py` to store temporary prompt files inside `run_dir/.tmp` rather than a hardcoded global directory.
2. **Automated Skill Linking**: Update `deploy.sh` to use the `--consent` flag when linking skills via the Gemini CLI.
3. **Explicit CLI Arguments**: 
   - Add `--engine` and `--model` arguments ONLY to `orchestrator.py` and manually invoked entrypoint scripts.
   - `orchestrator.py` must forward these arguments via process-level environment variables, ensuring top-level observability without internal API pollution.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Deployment Scripts Modification**: 
  - Locate `gemini skills link "$PROD_DIR"` in `deploy.sh`. Append the `--consent` flag. (Note: `kit-deploy.sh` does not invoke this command, so it requires no changes).
- **Hierarchical Configuration Resolution**:
  - In `scripts/agent_driver.py`, implement a robust hierarchical fallback: `(Environment Variable) > (config.py default)`. This ensures that even if environment variables are purged (as in `test_config_externalization`), the system remains robust and backward compatible. NEVER remove fallback logic from the core driver.
- **CLI Argument Parsing & State Broadcasting**:
  - Update `argparse` configuration ONLY in `scripts/orchestrator.py` and any standalone entrypoint scripts (e.g., `scripts/spawn_auditor.py`).
  - Add `--engine` and `--model` with help strings.
  - **Dynamic Environment Awareness**: To prevent the "State Clobbering" anti-pattern, the `default` value for these argparse arguments must be environment-aware: `default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE)`. This ensures that when a script is run as a subprocess (inheriting state), it does not accidentally overwrite parent configurations with static defaults.
  - Only modify `os.environ` if the argument was explicitly provided via CLI, or ensure the assignment is idempotent relative to the inherited state.
  - Rely on standard environment variable inheritance to propagate these settings cleanly to `agent_driver.py` and child `spawn_*.py` processes.
  - **CRITICAL FIX**: `spawn_coder.py` currently uses a hardcoded `openclaw_agent_call` (which directly invokes the `openclaw` binary) for interactive feedback loops. Refactor `spawn_coder.py` to replace `openclaw_agent_call` with `invoke_agent` from `agent_driver.py`, ensuring the Coder respects the inherited `LLM_DRIVER` (e.g., Gemini) globally instead of overriding it.
- **JIT Prompt Isolation (`agent_driver.py`)**:
  - Update the `invoke_agent` function signature to accept an optional `run_dir` parameter.
  - If `run_dir` is provided and it exists, `temp_dir = os.path.join(run_dir, ".tmp")`. Otherwise, rely on standard OS mechanisms (`import tempfile`, then `temp_dir = tempfile.gettempdir()`) to prevent Environment Coupling anti-patterns. NEVER hardcode absolute paths like `~/.openclaw/workspace`.
  - Ensure `os.makedirs(temp_dir, exist_ok=True)` is called.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** Temp prompt files are isolated per run.
  - **Given** an SDLC run is triggered with a specific `run_dir`.
  - **When** a sub-agent is spawned.
  - **Then** the temporary `sdlc_prompt_*.txt` file is created inside `[run_dir]/.tmp/`.

- **Scenario 2:** Headless deployment completes without stalling.
  - **Given** a clean system.
  - **When** `./deploy.sh` or `./kit-deploy.sh` is executed.
  - **Then** the Gemini CLI skill linking succeeds immediately without waiting for a `[Y/n]` prompt.

- **Scenario 3:** Explicit CLI parameters dictate execution engine at the orchestrator level.
  - **Given** the command `python3 orchestrator.py ... --engine gemini --model gemini-3.1-pro-preview`.
  - **When** the pipeline runs.
  - **Then** the orchestrator properly logs the configured engine parameters via the `execution_log_msg` defined in Section 7, and explicitly sets the environment variables so that all downstream scripts cleanly inherit and execute using the `gemini` CLI and the specified model without hardcoded fallbacks.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: 
  - Update `tests/test_gemini_agent_driver.py` to verify the new `run_dir` logic in `invoke_agent`.
- **Integration/E2E Testing**:
  - Update bash integration tests (e.g., `test_034_dual_deploy.sh`) to ensure `--consent` doesn't break the CLI syntax.
  - **CRITICAL Coder Interactive Loop Test**: Implement a specific mock test (e.g. `tests/test_spawn_coder_refactor.py` or bash equivalent) to simulate a Reviewer rejecting a PR, ensuring that the refactored `invoke_agent` in `spawn_coder.py` successfully handles iterative feedback loops without crashing.
  - Run `orchestrator.py` in test mode using the explicit `--engine` flag to ensure end-to-end parameter propagation works.

## 6. Framework Modifications (框架防篡改声明)
- `deploy.sh`
- `scripts/orchestrator.py`
- `scripts/spawn_*.py` (all spawn scripts)
- `scripts/agent_driver.py`
- `scripts/config.py`

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

- **For Execution Verification Log in `orchestrator.py`**:
```python
execution_log_msg = f"Orchestrator Engine Configured -> Engine: {args.engine}, Model: {args.model}"
```

- **For `scripts/config.py` (Define system constants)**:
```python
# System-wide configuration constants
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_LLM_ENGINE = "openclaw"
```

- **For Deployment Scripts (Gemini Link command in `deploy.sh`)**:
```bash
gemini skills link "$PROD_DIR" --consent
```

- **For CLI Help Texts (argparse)**:
```python
parser.add_argument("--engine", choices=["openclaw", "gemini"], default=config.DEFAULT_LLM_ENGINE, help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})")
parser.add_argument("--model", default=config.DEFAULT_GEMINI_MODEL, help=f"Model to use when --engine is gemini (default: {config.DEFAULT_GEMINI_MODEL})")
```