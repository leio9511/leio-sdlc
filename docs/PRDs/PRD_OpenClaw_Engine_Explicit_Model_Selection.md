---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: OpenClaw Engine Explicit Model Selection

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` now supports an `openclaw` execution path that routes SDLC execution roles through a dedicated isolated agent identity:
- `sdlc-generic-openclaw`

This architecture successfully solved the primary startup-context contamination problem by moving execution away from the main qbot workspace and onto an isolated agent workspace.

However, live validation exposed a new deterministic-control defect:
- SDLC can be launched with `--engine openclaw --model <requested_model>`
- but the current `agent_driver.py` implementation applies the requested model only when `sdlc-generic-openclaw` is first created via `openclaw agents add --model <model> ...`
- once that agent already exists, later runs reuse it without rebinding or overriding its model
- subsequent invocation uses `openclaw agent --agent sdlc-generic-openclaw ...` with no model override path

This creates a severe configuration illusion:
- a user can explicitly request `--model gpt`
- the orchestrator can print `Engine: openclaw, Model: gpt`
- but planner/coder/reviewer may still actually run on the pre-existing agent's old bound model (for example `gemini-3.1-pro-preview`)

That is not merely cosmetic. It breaks determinism for:
- smoke tests,
- engine/model validation,
- reproducibility of SDLC runs,
- safe comparison between model behaviors under the same engine.

The current workaround, deleting `sdlc-generic-openclaw` before a run, is operationally useful for one-off validation but is not an acceptable steady-state design.

This PRD therefore defines the correct architecture for deterministic model selection when using the `openclaw` engine.

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. When SDLC is launched with `--engine openclaw --model <requested_model>`, the effective OpenClaw execution roles must actually run with that requested model.
2. The system must not silently reuse an already-existing generic OpenClaw agent bound to a different model.
3. OpenClaw engine routing must remain isolated from the main workspace persona/bootstrap context.
4. Planner, Coder, Reviewer, and Verifier must all resolve through a model-consistent OpenClaw execution identity under the same run.
5. The implementation must support repeated runs with different requested models without requiring manual deletion of the generic agent.
6. The runtime must fail fast if a model mismatch is detected in a way that would otherwise violate deterministic execution.

### Non-Functional Requirements
1. The solution must remain low-blast-radius and localized to the OpenClaw adapter path.
2. The solution must preserve current startup-context isolation behavior.
3. The solution must preserve engine routing transparency in logs and notifications.
4. The solution must be testable through deterministic mocked checks plus at least one live smoke-test path.

### Explicit Boundaries
- **In Scope**:
  - OpenClaw engine model resolution semantics
  - generic isolated agent identity strategy
  - OpenClaw adapter behavior in `agent_driver.py`
  - supporting tests for deterministic model selection
  - fail-fast behavior for model mismatch
- **Out of Scope**:
  - Gemini engine model routing
  - broad engine-registry redesign
  - replacing OpenClaw CLI transport with Gateway RPC
  - unrelated notification or reviewer/coder prompt improvements
  - redesign of the generic isolated workspace bootstrap files themselves

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Root Cause
The current implementation conflates two different identities:
1. the isolated execution environment identity
2. the requested execution model identity

Today the OpenClaw path hardcodes one fixed agent id:
- `sdlc-generic-openclaw`

Creation path:
- if missing, create `sdlc-generic-openclaw` with `--model <requested_model>`

Execution path:
- always invoke `openclaw agent --agent sdlc-generic-openclaw ...`

This means the first model used to create the agent wins, and later explicit model requests are not deterministically honored.

### 3.2 Recommended Solution: Model-Aware Agent Identity
The correct design is to make the isolated OpenClaw execution agent identity model-aware.

Instead of one fixed id, derive the OpenClaw execution agent id from the resolved requested model.

Examples:
- requested model `gpt` -> `sdlc-generic-openclaw-gpt`
- requested model `gemini-3.1-pro-preview` -> `sdlc-generic-openclaw-gemini-3-1-pro-preview`

This yields the following properties:
1. each model gets a deterministic isolated execution agent identity,
2. agent creation remains lazy,
3. repeated runs with the same model reuse the same isolated agent,
4. runs with different requested models do not accidentally reuse a stale agent bound to the wrong model,
5. startup-context isolation remains intact because each model-specific agent still has its own isolated workspace template.

### 3.3 Why This Is Better Than Auto-Recreate-On-Mismatch
A smaller patch would be:
- if existing `sdlc-generic-openclaw` model != requested model, delete and recreate it.

That approach is rejected as the main architecture because:
1. it is destructive,
2. it risks interfering with concurrent or recent runs,
3. it turns model switching into a mutable global singleton race,
4. it treats model identity as an afterthought rather than part of execution identity.

The preferred architecture is therefore:
- **model-aware named agents**, not a single mutable shared agent.

### 3.4 Fail-Fast Guardrail
Even with model-aware agent ids, the runtime must still validate consistency.

If the resolved agent id already exists but OpenClaw reports a different bound model than the requested model, the runtime must fail fast rather than proceed ambiguously.

This protects against:
- manual agent drift,
- registry corruption,
- partial migrations,
- stale assumptions in future code changes.

### 3.5 Authorized File Targets
The intended file targets are narrowly limited to:
- `scripts/agent_driver.py`
- `scripts/config.py` if needed for clearer OpenClaw-specific model defaults/constants
- test files directly covering model-aware OpenClaw routing and mismatch protection

The implementation should avoid unnecessary changes in orchestrator, prompt playbooks, or unrelated engine paths.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: First OpenClaw run creates a model-specific isolated agent**
  - **Given** no OpenClaw isolated execution agent exists for requested model `gpt`
  - **When** SDLC is launched with `--engine openclaw --model gpt`
  - **Then** the runtime lazily creates a model-specific isolated OpenClaw agent for `gpt` and uses it for execution

- **Scenario 2: Repeated OpenClaw runs with the same model reuse the same model-specific agent**
  - **Given** a model-specific OpenClaw isolated agent already exists for requested model `gpt`
  - **When** another SDLC run starts with `--engine openclaw --model gpt`
  - **Then** the runtime reuses that same `gpt`-bound isolated agent without recreating it

- **Scenario 3: Different requested models do not reuse a stale agent bound to another model**
  - **Given** a `gpt`-bound OpenClaw isolated agent already exists
  - **When** SDLC starts with `--engine openclaw --model gemini-3.1-pro-preview`
  - **Then** the runtime does not reuse the `gpt` agent and instead resolves a separate model-specific agent for Gemini

- **Scenario 4: Model mismatch fails fast**
  - **Given** the runtime resolves a model-specific OpenClaw agent id
  - **And** OpenClaw reports that the existing agent is bound to a different model than requested
  - **When** execution begins
  - **Then** the runtime stops with a fatal deterministic-model-mismatch error instead of silently continuing

- **Scenario 5: Context isolation remains preserved**
  - **Given** SDLC is launched through the OpenClaw engine using a model-specific isolated agent
  - **When** Planner/Coder/Reviewer execute the PRD
  - **Then** they run through the isolated OpenClaw agent workspace rather than the main qbot workspace

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
The core quality risk is configuration illusion: logs and CLI arguments may claim one model while execution silently happens on another.

Therefore the testing strategy must focus on deterministic routing and identity correctness.

### Recommended Verification Strategy
1. **Mocked adapter tests**
   - verify agent id derivation from requested model
   - verify create path uses the requested model
   - verify existing matching agent is reused
   - verify mismatched existing agent triggers fail-fast

2. **Focused integration-level checks**
   - verify OpenClaw command construction uses the resolved model-specific agent id
   - verify non-OpenClaw engine paths remain unchanged

3. **Live smoke validation**
   - start from a state where the target model-specific agent does not yet exist
   - run a very small PRD using `--engine openclaw --model <target>`
   - verify `openclaw agents list` shows the recreated agent with the correct model
   - verify planner/coder/reviewer all route through that same model-specific agent
   - verify no main-workspace context contamination symptoms appear

### Quality Goal
After implementation, `--engine openclaw --model X` must mean exactly one thing operationally:
- the SDLC run actually executes on model `X`
- not just at creation time,
- not just in logging,
- but in the effective isolated OpenClaw execution identity used by the run.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/config.py` (only if needed for OpenClaw-specific model naming/default clarity)
- test files covering OpenClaw adapter routing/model semantics

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Capture ISSUE-1181 as a deterministic model-selection defect in the OpenClaw engine path. The trigger was a live run launched with `--engine openclaw --model gpt` that still reused an existing isolated agent bound to `gemini-3.1-pro-preview`.
- **Rejected Direction**: Auto-delete and recreate a single shared `sdlc-generic-openclaw` agent on model mismatch. This was rejected as the main architecture because it is destructive and unsafe under repeated or concurrent use.
- **v2.0 Direction**: Promote model identity into the isolated agent identity itself, using model-aware named OpenClaw agents plus fail-fast consistency checks.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`deterministic_model_mismatch_error`**:
```text
[FATAL] OpenClaw isolated agent model mismatch. Requested model '{requested_model}', but agent '{agent_id}' is bound to '{actual_model}'. Refusing to continue with non-deterministic execution.
```

- **Model-aware agent id examples (semantic contract)**:
```text
sdlc-generic-openclaw-gpt
sdlc-generic-openclaw-gemini-3-1-pro-preview
```
