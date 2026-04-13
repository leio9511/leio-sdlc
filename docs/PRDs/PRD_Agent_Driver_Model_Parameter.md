---
Affected_Projects: [leio-sdlc]
---

# PRD: Add --model Parameter to agent_driver.py for Flexible Model Configuration

## 1. Context & Problem (业务背景与核心痛点)
The SDLC pipeline currently relies on a hardcoded or default model selection mechanism. When `LLM_DRIVER=openclaw`, the sub-agents (Coder, Reviewer, Auditor, etc.) always use the OpenClaw global default model, with no easy way to override or specify a different model per invocation. When `LLM_DRIVER=gemini`, only the `TEST_MODEL` environment variable is available, which is not convenient for runtime flexibility.

**Boss Requirement:** Add a `--model` parameter to `agent_driver.py` so that model selection is explicit, flexible, and controllable at invocation time. This enables the SDLC orchestrator to inherit the parent session's model automatically.

## 2. Requirements & User Stories (需求定义)
1. **CLI Parameter**: Add `--model` argument to `agent_driver.py`'s `build_prompt()` function signature.
2. **Environment Variable Fallback**: If `--model` is not provided, fall back to `TEST_MODEL` environment variable (existing behavior).
3. **Default Behavior**: If neither `--model` nor `TEST_MODEL` is set, use the OpenClaw global default.
4. **Propagation to Sub-Agents**: The `orchestrator.py` should detect the parent session's current model and pass it via `--model` to all `spawn_*` scripts.
5. **Gemini Driver Support**: When `LLM_DRIVER=gemini`, the `--model` parameter should override the `TEST_MODEL` environment variable.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target File**: `scripts/agent_driver.py`
- **Function Signature Change**: `build_prompt(role, workdir, ..., model=None)` — add `model` parameter.
- **Model Resolution Priority**:
  1. Explicit `--model` CLI argument (highest priority)
  2. `TEST_MODEL` environment variable
  3. OpenClaw global default
- **Orchestrator Integration**: The orchestrator should call `openclaw sessions list` or inspect `OPENCLAW_MODEL` env var to detect the parent model's identity, then pass it to all `spawn_*` scripts via their respective CLI interfaces.
- **Propagation Path**: `orchestrator.py` → `spawn_coder.py` / `spawn_reviewer.py` / `spawn_auditor.py` → `agent_driver.build_prompt(..., model=xxx)`

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Given `LLM_DRIVER=openclaw` and `--model minimax/MiniMax-M2.7-highspeed` is passed; When `invoke_agent()` is called; Then the command invokes `openclaw agent --model minimax/MiniMax-M2.7-highspeed ...`.
- **Scenario 2**: Given no `--model` argument and `TEST_MODEL=google/gemini-2.5-pro`; When `LLM_DRIVER=gemini`; Then Gemini driver uses `google/gemini-2.5-pro`.
- **Scenario 3**: Given orchestrator is running on `minimax/MiniMax-M2.7-highspeed`; When a new PR is spawned; Then the Coder subprocess uses `--model minimax/MiniMax-M2.7-highspeed`.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Mock `subprocess.run` to verify correct `--model` flag is passed to the `openclaw agent` CLI command.
- **Integration Testing**: Run a sandbox SDLC pipeline and verify that sub-agents inherit the correct model from the parent session.
- **Regression Testing**: Ensure existing `LLM_DRIVER=gemini` behavior with `TEST_MODEL` is unaffected.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/orchestrator.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_verifier.py`

## 7. Hardcoded Content (硬编码内容)
- CLI argument: `--model`
- Environment variable fallback: `TEST_MODEL`
- Agent flag: `--model`
- Gemini exec flag: `--model` (via `gemini run --model <MODEL>`)
