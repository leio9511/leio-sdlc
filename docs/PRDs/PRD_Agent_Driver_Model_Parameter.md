---
Affected_Projects: [leio-sdlc]
---

# PRD: Add --model Parameter to agent_driver.py for Flexible Model Configuration

## 1. Context & Problem (业务背景与核心痛点)
The SDLC pipeline currently relies on a hardcoded or default model selection mechanism. When `LLM_DRIVER=openclaw`, the sub-agents (Coder, Reviewer, Auditor, etc.) always use the OpenClaw global default model, with no easy way to override or specify a different model per invocation. When `LLM_DRIVER=gemini`, only the `TEST_MODEL` environment variable is available, which is not convenient for runtime flexibility.

**Design Decision:** Model inheritance is achieved via **explicit parameter passing**, NOT environment variable detection. The Orchestrator receives the model name as a `--model` argument at startup, and propagates it to all sub-scripts via their CLI interfaces. This avoids fragile CLI parsing of `openclaw sessions list` output.

## 2. Requirements & User Stories (需求定义)
1. **Orchestrator `--model` Argument**: The orchestrator accepts a `--model` CLI argument specifying which model to use for all sub-agents.
2. **Sub-Script Propagation**: All `spawn_*` scripts (`spawn_coder.py`, `spawn_reviewer.py`, `spawn_auditor.py`, `spawn_verifier.py`) accept a `--model` argument and pass it to `agent_driver`.
3. **agent_driver `--model` Parameter**: `build_prompt()` and `invoke_agent()` in `agent_driver.py` accept a `model` parameter.
4. **Gemini Driver Support**: When `LLM_DRIVER=gemini`, the `--model` parameter overrides `TEST_MODEL`.
5. **Backward Compatibility**: If no `--model` is provided, fall back to `TEST_MODEL` env var for Gemini, or OpenClaw default for openclaw driver.

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

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Given `orchestrator.py --model minimax/MiniMax-M2.7-highspeed`; When a Coder subprocess is spawned; Then `spawn_coder.py` receives `--model minimax/MiniMax-M2.7-highspeed` and the agent uses that model.
- **Scenario 2**: Given `LLM_DRIVER=gemini` and `--model google/gemini-2.5-pro`; When `invoke_agent()` is called; Then the Gemini CLI is invoked with `gemini run --model google/gemini-2.5-pro ...`.
- **Scenario 3**: Given no `--model` argument and `TEST_MODEL=google/gemini-2.5-pro`; When `LLM_DRIVER=gemini`; Then Gemini driver uses `google/gemini-2.5-pro` (backward compatible fallback).
- **Scenario 4**: Given orchestrator running on `google/gemini-3.1-pro-preview`; When spawning multiple PRs; Then all sub-agents consistently use `google/gemini-3.1-pro-preview`.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Mock `subprocess.run` to verify correct `--model` flag is passed to the `openclaw agent` CLI command.
- **Integration Testing**: Run a sandbox SDLC pipeline with explicit `--model` and verify sub-agents use the specified model.
- **Regression Testing**: Ensure existing `LLM_DRIVER=gemini` behavior with `TEST_MODEL` is unaffected.

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
- Spawn script CLI argument: `--model`
- Agent flag: `--model` (e.g., `openclaw agent --model <name>`)
- Environment variable fallback: `TEST_MODEL`
- Gemini exec flag: `--model` (e.g., `gemini run --model <MODEL>`)
