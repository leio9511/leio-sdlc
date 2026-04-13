---
Affected_Projects: [leio-sdlc]
---

# PRD: Add --model Parameter to agent_driver.py for Flexible Model Configuration

## 1. Context & Problem (业务背景与核心痛点)
The SDLC pipeline currently relies on a hardcoded or default model selection mechanism. When `LLM_DRIVER=openclaw`, the sub-agents (Coder, Reviewer, Auditor, etc.) always use the OpenClaw global default model, with no easy way to override or specify a different model per invocation. When `LLM_DRIVER=gemini`, only the `TEST_MODEL` environment variable is available, which is not convenient for runtime flexibility.

**Design Decision:** Model inheritance is achieved via **explicit parameter passing**, NOT environment variable detection. The Orchestrator requires an explicit `--model` argument, which serves as self-documenting instructions to the Manager (agent) about how to launch the pipeline.

## 2. Requirements & User Stories (需求定义)
1. **Orchestrator `--model` Argument (Required)**: The orchestrator accepts a **required** `--model` CLI argument. If not provided, it exits with error: `"必须指定 SDLC 使用的模型，要么是 Boss 指定的模型，如果 Boss 没有指定，就用当前 Session 所用的模型"`.
2. **Self-Documenting Help**: `--model`'s help text is exactly: `"指定 SDLC 使用的模型，要么是 Boss 指定的模型，如果 Boss 没有指定，就用当前 Session 所用的模型"`.
3. **Manager Self-Awareness**: The Manager (agent) reads its current session model via `session_status`, and passes it as `--model` when launching the orchestrator. If Boss specifies a model, use Boss's; otherwise use current session model.
4. **Sub-Script Propagation**: All `spawn_*` scripts (`spawn_coder.py`, `spawn_reviewer.py`, `spawn_auditor.py`, `spawn_verifier.py`) accept a `--model` argument and pass it to `agent_driver`.
5. **agent_driver `--model` Parameter**: `build_prompt()` and `invoke_agent()` in `agent_driver.py` accept a `model` parameter.
6. **Gemini CLI Special Handling**: When `LLM_DRIVER=gemini` and the provided `--model` is not a valid Gemini model identifier, the system silently ignores the value and uses Gemini CLI's own default model (no error thrown).
7. **Backward Compatibility**: If no `--model` is provided, fall back to `TEST_MODEL` env var for Gemini, or OpenClaw default for openclaw driver.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target Files**: `scripts/agent_driver.py`, `scripts/orchestrator.py`, all `spawn_*.py` scripts.
- **Model Resolution Priority** (for each sub-agent invocation):
  1. Explicit `--model` CLI argument passed to the spawn script (highest priority)
  2. `TEST_MODEL` environment variable (Gemini driver only)
  3. OpenClaw global default (fallback)
- **No env-var detection of parent model**: We do NOT parse `openclaw sessions list` or rely on `OPENCLAW_MODEL`. The model is injected top-down via CLI args.
- **Orchestrator startup**: The Manager launches orchestrator with `--model <current-session-model>`, e.g. `--model minimax/MiniMax-M2.7-highspeed`.
- **Propagation chain**: `orchestrator.py --model XXX` → reads `args.model` → passes to `spawn_coder.py --model XXX` → passes to `agent_driver.build_prompt(..., model=XXX)` → `invoke_agent(..., model=XXX)`.
- **OpenClaw agent invocation**: When `model` is not None, call `openclaw agent --model <model> ...` instead of just `openclaw agent ...`.
- **Gemini validation**: If `LLM_DRIVER=gemini` and `model` is not a recognized Gemini model string, silently fall back to Gemini CLI default.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Given orchestrator is started without `--model`; When launched; Then it exits with error message containing `"必须指定 SDLC 使用的模型，要么是 Boss 指定的模型，如果 Boss 没有指定，就用当前 Session 所用的模型"`.
- **Scenario 2**: Given `orchestrator.py --model minimax/MiniMax-M2.7-highspeed`; When a Coder subprocess is spawned; Then `spawn_coder.py` receives `--model minimax/MiniMax-M2.7-highspeed` and the agent uses that model.
- **Scenario 3**: Given `LLM_DRIVER=gemini` and `--model google/gemini-2.5-pro`; When `invoke_agent()` is called; Then the Gemini CLI is invoked with `gemini run --model google/gemini-2.5-pro ...`.
- **Scenario 4**: Given no `--model` argument and `TEST_MODEL=google/gemini-2.5-pro`; When `LLM_DRIVER=gemini`; Then Gemini driver uses `google/gemini-2.5-pro` (backward compatible fallback).
- **Scenario 5**: Given orchestrator running on `google/gemini-3.1-pro-preview`; When spawning multiple PRs; Then all sub-agents consistently use `google/gemini-3.1-pro-preview`.
- **Scenario 6**: Given `LLM_DRIVER=gemini` and `--model minimax/MiniMax-M2.7-highspeed` (not a Gemini model); When `invoke_agent()` is called; Then the invalid model is silently ignored and Gemini CLI default is used (no error thrown).

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Mock `subprocess.run` to verify correct `--model` flag is passed to the `openclaw agent` CLI command.
- **Integration Testing**: Run a sandbox SDLC pipeline with explicit `--model` and verify sub-agents use the specified model.
- **Regression Testing**: Ensure existing `LLM_DRIVER=gemini` behavior with `TEST_MODEL` is unaffected.
- **Negative Testing**: Verify that missing `--model` causes an immediate exit with the specified error message.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/orchestrator.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_planner.py`

## 7. Hardcoded Content (硬编码内容)
- Orchestrator CLI argument: `--model`
- Help text: `"指定 SDLC 使用的模型，要么是 Boss 指定的模型，如果 Boss 没有指定，就用当前 Session 所用的模型"`
- Error message: `"必须指定 SDLC 使用的模型，要么是 Boss 指定的模型，如果 Boss 没有指定，就用当前 Session 所用的模型"`
- Spawn script CLI argument: `--model`
- Agent flag: `--model` (e.g., `openclaw agent --model <name>`)
- Environment variable fallback: `TEST_MODEL`
- Gemini exec flag: `--model` (e.g., `gemini run --model <MODEL>`)
