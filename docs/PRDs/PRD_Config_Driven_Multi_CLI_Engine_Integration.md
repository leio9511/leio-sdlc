---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Config_Driven_Multi_CLI_Engine_Integration

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` already supports more than one execution path, but engine behavior is still encoded as provider-specific business logic inside the runtime. Today the system has first-class knowledge of OpenClaw-native execution and Gemini CLI behavior. Codex now needs to be onboarded as an additional engine.

The real requirement is not “add Codex support.” The real requirement is to evolve `leio-sdlc` into a provider-agnostic, config-driven, hot-pluggable engine runtime.

The current model creates six concrete risks:
1. **Engine onboarding cost scales linearly with code edits.** Every new CLI tends to require new conditional logic in `agent_driver.py` and related entrypoints.
2. **Open-source / private boundary is unstable.** Future private corporate CLIs must not require their names, arguments, or invocation details to be committed into the public repository.
3. **Continuity assumptions are underspecified.** The system currently mixes together two different questions:
   - whether an engine is stateful enough for a role,
   - how the provider-native session handle is acquired.
4. **Role safety is ambiguous.** Revision-heavy coder loops require real continuity and must not silently degrade to stateless execution.
5. **Control-plane behavior is at risk during refactor.** This is a core SDLC runtime path. If the engine abstraction is changed carelessly, existing OpenClaw and Gemini workflows may break.
6. **Public examples can accidentally become architecture.** If OpenClaw, Gemini, and Codex are treated as hard-coded architectural identities rather than example engines under a generic contract, the system will remain only partially configurable.

This PRD therefore defines the final iteration-1 contract:
- preserve the existing SDLC control plane,
- move engine selection to a config-driven registry,
- separate **continuity mode** from **native-handle acquisition strategy**,
- support OpenClaw, Gemini, and Codex as the initial public conformance matrix,
- allow future private engines to be added through runtime-only config overlays,
- forbid public-code dependence on private provider names.

This is a final execution-grade contract, not a discussion placeholder.

### 1.1 Status Delta Since Original Approval
Since the original approval of this PRD, the OpenClaw baseline has materially advanced and that changes how this document should be interpreted:
- execution-role startup context contamination under the OpenClaw path has been remediated through isolated execution routing,
- explicit model selection under the OpenClaw engine has been implemented and deployed, eliminating the earlier non-determinism where a reused generic agent could silently retain an old model binding,
- live OpenClaw + GPT validation has already passed at two levels: an Auditor smoke test and a full SDLC smoke test that completed planner / coder / reviewer / merge flow and UAT,
- therefore Codex is no longer being onboarded onto an unstable or ambiguous OpenClaw substrate. The remaining question is third-engine conformance under an already validated OpenClaw baseline, not first-principles rescue of the engine layer.

### 1.2 Current-Code Reality vs Target-State Contract
The current codebase has not yet completed the provider-agnostic runtime described by this PRD.
Today, the production path still primarily relies on environment-driven engine selection and provider-specific branching centered on `LLM_DRIVER`, while the config-driven engine registry remains a partial and transitional substrate.
Accordingly, this PRD must be read as a target-state execution contract for replacing that current branching model, not as a claim that the present implementation already satisfies every registry, continuity, or Codex-runtime requirement described below.

## 2. Requirements & User Stories (需求定义)
1. **Public Core Schema + Public Examples + Local Runtime Overlay**
   - The repo must ship a public schema-bearing template at `config/sdlc_config.json.template`.
   - The public template may include public example engines such as `openclaw`, `gemini`, and `codex`, but those examples must not be treated as the architecture’s full universe of legal engine identities.
   - The installed runtime may load a local overlay at `config/sdlc_config.json`.
   - Private engines may exist only in the runtime overlay and must not be required in tracked public source.
   - Public code must treat provider identity as config data, not as a hard-coded architectural constant.

2. **Engine Registry**
   - The system must load engines from an explicit registry under `engines`.
   - Iteration 1 must support these public example engine ids as the initial conformance matrix:
     - `openclaw`
     - `gemini`
     - `codex`
   - Future private engines may be added if and only if they satisfy the same engine-spec contract.

3. **Two Engine Kinds Only in Iteration 1**
   - `builtin_openclaw`
   - `generic_external_cli`
   - OpenClaw remains a built-in runtime kind, but it must still be selected through the same registry path as all other engines.
   - Gemini and Codex must both use the same `generic_external_cli` contract.
   - The orchestrator and role entrypoints must depend on resolved engine capabilities, not provider names.

4. **Exact Engine Spec Contract**
   - Every engine entry must define the required contract fields listed in Section 7.
   - Missing required keys, invalid enum values, malformed arrays, or invalid command-template shapes must fail at startup before any sub-agent is invoked.
   - The public core contract must be sufficient to express a new private engine without adding a provider-specific branch, enum, or hard-coded engine id to public code.

5. **Continuity Must Be Modeled in Two Layers**
   - Every engine must declare exactly one `continuity_mode`:
     - `stateful`
     - `stateless`
   - Every engine must also declare exactly one `handle_acquisition_strategy`:
     - `caller_assigned_handle`
     - `emitted_handle_on_start`
     - `deterministic_post_start_discovery`
     - `none`
   - `continuity_mode` answers whether the engine can safely continue a prior session.
   - `handle_acquisition_strategy` answers how the provider-native handle is obtained on the first turn.

6. **Role Compatibility Must Be Explicit**
   - Every engine must declare `allowed_roles`.
   - The selected engine must be rejected if the current role is not in `allowed_roles`.
   - Iteration 1 role rules are:
     - `coder` requires `continuity_mode = stateful`
     - `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator` may use either `stateful` or `stateless` engines if the engine explicitly allows that role
     - `stateless` engines are forbidden for `coder`

7. **Engine Resolution Order**
   - Engine resolution precedence must be exact:
     1. explicit role-level override in code path if a script passes one,
     2. runtime config `role_overrides[role]`,
     3. runtime config `default_engine`,
     4. legacy environment fallback `LLM_DRIVER`,
     5. built-in constant from `scripts/config.py`.
   - Silent fallback to a different available engine is forbidden.

8. **Model Resolution Order**
   - Model resolution precedence must be exact:
     1. explicit CLI `--model` if provided and not equal to `auto`,
     2. explicit CLI `--model auto` resolved via engine `auto_model_behavior`,
     3. legacy environment fallback `SDLC_MODEL`,
     4. engine `default_model`,
     5. built-in constant from `scripts/config.py`.
   - For OpenClaw specifically, an explicit non-`auto` model request must resolve deterministically at launch time. Reusing a previously created runtime identity that remains bound to a different model without fail-fast detection is forbidden.

9. **Exact `auto` Semantics**
   - `auto` is a semantic request, not a universal literal.
   - Iteration 1 behaviors are:
     - for `openclaw`, `auto_model_behavior = "omit_flag"`, meaning SDLC does not pass a model flag and lets the OpenClaw runtime/session default decide;
     - for `gemini` and `codex`, `auto_model_behavior = "use_default_model"`, meaning SDLC resolves `auto` to the engine’s `default_model` and passes that value through the configured model arg.

10. **Unified Logical Session Lifecycle**
    - SDLC must own a stable `logical_session_key` for each role / PR loop.
    - For stateful engines, SDLC must persist a mapping:
      - `logical_session_key -> native_handle`
    - A native handle must be acquired exactly once for a fresh logical session and reused on all later turns.

11. **Initial Public Conformance Matrix**
    - OpenClaw, Gemini, and Codex are the three required public engine fixtures for iteration 1.
    - They must all be validated through the same engine registry and normalized contract.
    - Their purpose is to prove the abstraction is generic, not to make provider-specific branching permanent.
    - Public example config must remain conservative: conformance fixtures may exist in the public template without becoming default production role bindings.

12. **Gemini Continuity Scope in Iteration 1**
    - Gemini is approved for `coder`, `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator`.
    - Gemini must use `continuity_mode = stateful` and `handle_acquisition_strategy = deterministic_post_start_discovery`.
    - The discovery path must use provider-native session listing and session-set diffing in an isolated project/worktree context.
    - Same-project concurrent fresh Gemini bootstrap for multiple logical sessions is forbidden unless serialized by a runtime lock or equivalent per-project guard.
    - Prompt-text or temp-file-path matching is explicitly recognized as transitional scaffolding, not the target architecture.

13. **Codex Continuity Scope in Iteration 1**
    - Codex is architecturally compatible with `coder`, `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator`, because local validation confirms a resumable path via `codex exec` plus `codex exec resume`.
    - Codex must use `continuity_mode = stateful` and `handle_acquisition_strategy = emitted_handle_on_start`.
    - However, Codex coder rollout is gated by completion of the Mandatory Baseline Validation Phase. Iteration-1 architecture may support Codex coder continuity, but production-facing role defaults and rollout decisions must remain conservative until OpenClaw and Gemini baselines are proven stable under the new engine architecture.

14. **Fail-Fast Observability**
    - Unavailable commands, invalid configs, invalid role bindings, failed handle acquisition, and unsupported continuity must fail with the exact strings defined in Section 7.
    - The system must not continue with degraded behavior.

15. **Regression-Safety Requirement**
    - This refactor is not allowed to change SDLC control-plane behavior without explicit authorization.
    - Required safety target:
      - existing OpenClaw-driven SDLC flows continue to behave normally,
      - existing OpenClaw deterministic explicit-model-selection behavior remains preserved,
      - existing Gemini-driven SDLC flows continue to behave normally,
      - Codex is added as a third conformance case under the same engine contract.

16. **Scope Restraint**
    - This PRD modifies only engine selection, config loading, capability validation, handle acquisition, continuity persistence, and CLI rendering contracts.
    - It does not authorize broad orchestrator state-machine redesign, skill-router redesign, or unrelated prompt-contamination remediation.

17. **Post-1181 Baseline Interpretation**
    - For this PRD's rollout and acceptance, OpenClaw must be treated as an already validated baseline for isolated execution routing and deterministic explicit model selection.
    - Codex onboarding must be measured against that post-1181 baseline, not against older singleton-agent or best-effort model-binding assumptions.
    - Codex acceptance therefore requires contract parity in engine selection determinism, model resolution determinism, normalized start / resume behavior, and fail-fast observability.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Architectural Pattern
This is an agentic runtime routing problem. The correct pattern is:
- **Control Plane / Data Plane Separation**
  - the SDLC control plane owns role routing, PR state transitions, escalation, retries, and policy enforcement,
  - the engine data plane owns provider-specific command rendering, native-handle acquisition, and resume mechanics
- **Strategy Pattern** for engine invocation
- **Configuration-Driven Engine Registry** for engine definitions
- **Capability Gating** for role and continuity safety
- **Logical Session Ownership** for stable SDLC-side continuity
- **Conformance Test Matrix** to prove multiple engines satisfy the same contract

The anti-patterns being explicitly banned are:
- product-specific branching such as “if engine == gemini do X, if engine == codex do Y” across business logic outside the engine registry / renderer layer,
- making orchestrator state logic depend on provider name,
- treating public example engines as the architecture’s full identity model.

### 3.2 Runtime Shape
Iteration 1 must standardize the engine layer into exactly two runtime paths:
1. **`builtin_openclaw`**
   - implemented as a built-in engine renderer inside `agent_driver.py`
   - preserves first-class OpenClaw-native execution
   - still resolved through the same engine registry and config contract as other engines
2. **`generic_external_cli`**
   - implemented as a generic renderer driven entirely by engine spec fields
   - used for Gemini, Codex, and any future private CLI that conforms to the same contract

The key invariant is:
- the control plane must not care whether the resolved engine is OpenClaw, Gemini, Codex, or a future private engine,
- it may care only about validated engine capabilities and the normalized start / resume contract.

### 3.3 Configuration Layering
The configuration model must be explicitly understood as three layers:

1. **Public Core Schema Layer**
   - defines the engine contract shape, validation rules, precedence rules, merge rules, and normalized semantics
   - must be provider-agnostic except where a built-in runtime kind must exist for OpenClaw-native support

2. **Public Example Layer**
   - may include public example engine entries such as `openclaw`, `gemini`, and `codex`
   - exists to document supported public examples and to serve as the initial conformance matrix
   - must not be treated as the full required universe of engine identities

3. **Local Runtime Overlay Layer**
   - may define private engine ids, private commands, private arguments, private model defaults, and private role bindings
   - must be sufficient for private-engine onboarding without changing public code

The load path must be:
1. read `config/sdlc_config.json.template` from the repo / runtime as the public baseline,
2. if present, overlay `config/sdlc_config.json` from the installed runtime directory,
3. validate the merged result before any engine is selected.

The merge contract is fixed as follows:
- top-level object keys are merged by key, not whole-file replacement,
- `default_engine` is scalar override, so runtime overlay replaces template when present,
- `role_overrides` is merged by role name, with runtime overlay values overriding template values for matching roles,
- `engines` is merged by engine id, with runtime overlay allowed to both override existing engine entries and inject entirely new private engine ids,
- when the same engine id exists in both template and runtime overlay, object fields are merged by key with runtime overlay winning on conflicts,
- arrays are always replaced as whole values, never concatenated,
- setting a field to `null` in runtime overlay is not a deletion primitive unless a future PRD explicitly introduces deletion semantics.

### 3.4 Core Abstraction: Logical Session vs Native Handle
The engine layer must stop assuming that every provider supports caller-specified session ids.

The stable abstraction is:
- **logical session key**: owned by SDLC, stable across the role workflow
- **native handle**: owned by the provider CLI/runtime, used to continue the real underlying session

The runtime must persist a mapping from logical session key to native handle for every stateful engine.

This resolves the real provider differences:
- OpenClaw supports caller-assigned handles,
- Codex emits a handle on first run,
- Gemini requires deterministic one-time post-start discovery.

### 3.5 Required Engine Contract
Every engine entry must follow the exact JSON contract in Section 7. The required meaning of key fields is:
- `kind`: selects `builtin_openclaw` or `generic_external_cli`
- `command`: executable name or path used for availability and invocation
- `availability_check`: command array used to prove the engine exists before selection
- `allowed_roles`: authoritative allowlist for role binding
- `continuity_mode`: `stateful` or `stateless`
- `handle_acquisition_strategy`: how the native handle is obtained on the first turn
- `default_model`: engine-level fallback model
- `auto_model_behavior`: `omit_flag` or `use_default_model`
- `start`: invocation contract for a fresh session
- `resume`: invocation contract for a continued session
- `handle_capture`: strategy block used only when the native handle is not caller-assigned

### 3.6 Handle Acquisition Strategies
Iteration 1 recognizes exactly these strategies:

1. **`caller_assigned_handle`**
   - SDLC chooses the native handle before the first turn and passes it directly to the provider
   - used by `openclaw`

2. **`emitted_handle_on_start`**
   - the provider emits the native handle in structured output on the first run
   - SDLC parses and persists that handle
   - used by `codex`

3. **`deterministic_post_start_discovery`**
   - the provider creates a native handle on first run but does not emit it directly in the primary response path
   - SDLC must discover it once, deterministically, and persist it
   - used by `gemini`

4. **`none`**
   - only valid for `stateless` engines

### 3.7 Gemini Final Solution
Gemini is not allowed to remain on prompt-text or temp-file-path matching as the target design.

The required iteration-1 solution is:
1. before the first Gemini turn, collect the project-scoped session set via provider-native list command,
2. run the fresh Gemini start command,
3. collect the project-scoped session set again,
4. compute the set difference,
5. persist the newly created Gemini session id as the native handle for the logical session key,
6. use `-r <native_handle>` for all subsequent turns.

This requires isolated project / worktree context so that the set difference is deterministic.
Same-project concurrent fresh Gemini bootstrap is forbidden unless explicitly serialized by a runtime lock or equivalent per-project guard.

### 3.8 Codex Final Solution
Codex local validation has already confirmed, outside the current production runtime path, that:
- `codex exec` starts a session,
- structured JSON output emits `thread.started.thread_id`,
- `codex exec resume <thread_id>` continues the same thread,
- prior context is preserved across turns.

The current codebase does not yet implement this Codex continuity path end-to-end in the production runtime. This PRD authorizes bringing that validated provider capability into the unified engine contract.

Therefore, Codex must use:
- `continuity_mode = stateful`
- `handle_acquisition_strategy = emitted_handle_on_start`
- first turn: parse `thread_id` from structured output
- later turns: use `codex exec resume <thread_id>`

Codex is not being introduced here as an ad hoc provider-specific branch. It is being onboarded as the third public conformance fixture under the already-defined multi-engine runtime contract.
Its acceptance target is therefore stronger than “Codex can be invoked”:
- Codex must satisfy the same normalized engine-resolution, model-resolution, start / resume, handle-persistence, and fail-fast contracts already proven on the OpenClaw baseline,
- Codex-specific differences are allowed only in data-plane handle capture and CLI rendering semantics,
- production-facing enablement must remain conservative until Codex itself passes contract tests, smoke validation, and controlled full-chain validation under the unified runtime.

However, iteration-1 rollout must remain conservative:
- Codex coder support is part of the architecture contract,
- but production-facing enablement for coder must remain gated until the Mandatory Baseline Validation Phase has proven that the OpenClaw and Gemini baselines remain stable under the refactor, and until Codex has completed its own conformance and controlled live validation.

### 3.9 OpenClaw Final Solution
OpenClaw remains the cleanest path:
- `continuity_mode = stateful`
- `handle_acquisition_strategy = caller_assigned_handle`
- SDLC sets the session id directly
- no discovery step is required
- explicit non-`auto` model requests must land deterministically at launch time rather than inheriting stale provider-side bindings
- if the resolved OpenClaw runtime identity is incompatible with the requested model, the runtime must fail fast rather than silently continuing under the wrong model

### 3.10 Role Resolution
The runtime must resolve the effective engine per role using this exact algorithm:
1. if the active script explicitly passes an engine override for this role, use it,
2. else if `role_overrides[role]` exists in config, use it,
3. else use `default_engine`,
4. else if legacy env `LLM_DRIVER` exists, use it,
5. else fall back to the built-in constant from `scripts/config.py`.

After that selection, SDLC must validate:
1. engine id exists,
2. engine spec passes schema validation,
3. command exists via `availability_check`,
4. role is included in `allowed_roles`,
5. continuity mode is legal for the role,
6. handle acquisition strategy is legal for the continuity mode,
7. the start and resume contracts are valid for the declared strategy.

If any check fails, SDLC must stop with the exact fail-fast strings from Section 7.

### 3.11 Continuity Enforcement
Iteration 1 continuity behavior must be hard-coded at the policy level:
- `coder`
  - allowed: only `stateful`
  - forbidden: `stateless`
- `planner`, `reviewer`, `auditor`, `verifier`, `arbitrator`
  - allowed: whatever the engine explicitly declares in `allowed_roles`
  - `stateless` is allowed for these roles

This is intentionally conservative. It prevents the architecture from silently putting revision-critical coder loops onto a fresh-session CLI.

### 3.12 Model Resolution
The runtime must resolve the effective model with this exact algorithm:
1. if `--model <value>` is provided and `<value> != auto`, use `<value>`;
2. if `--model auto` is provided, apply engine `auto_model_behavior`;
3. else if legacy env `SDLC_MODEL` exists, use it;
4. else if the engine has `default_model` and that value is not `auto`, use it;
5. else if the engine has `default_model = auto`, apply `auto_model_behavior` exactly as if the caller had supplied `--model auto`;
6. else fall back to `scripts/config.py` default.

`auto_model_behavior` rules:
- `omit_flag`: do not pass a model flag to the CLI
- `use_default_model`: `default_model` must resolve to a concrete non-`auto` value before invocation; storing `default_model = auto` together with `use_default_model` is invalid and must fail with `engine_auto_model_invalid_default_error`

### 3.13 Handle Mapping Persistence and Lifecycle
The native-handle mapping for stateful engines must be treated as an explicit runtime contract, not an implementation detail.

Iteration 1 must enforce these rules:
- mapping persistence must live in the per-run runtime area, not in tracked repository files,
- the mapping key must include at least the logical session key and resolved engine id,
- a mapping entry may be created only after successful first-turn handle acquisition,
- resumed turns must read the stored handle instead of re-running bootstrap logic,
- cleanup, supersede, withdraw, and fatal teardown paths must clear stale mappings associated with the affected logical session,
- mappings from one PR / role loop must never be reused by another PR / role loop,
- concurrent runs must not be allowed to race on the same logical session mapping without a runtime lock or equivalent serialization.

This contract exists to prevent handle drift, cross-PR session contamination, and accidental continuation of the wrong provider session.

### 3.14 Rollout and Migration Strategy
This architecture change must be delivered as a staged migration, not as a single-step replacement.

Required rollout order:
1. **Characterization Phase**
   - First add or update tests that pin the current OpenClaw and Gemini behavior.
   - No architectural replacement is allowed before those regression baselines exist.
2. **Registry Introduction Phase**
   - Introduce the new engine registry and normalized contract while preserving existing OpenClaw and Gemini behavior.
   - At the end of this phase, the same SDLC workflows must still pass under OpenClaw and Gemini.
3. **Mandatory Baseline Validation Phase**
   - OpenClaw and Gemini must pass the mandatory regression suites before Codex is accepted as a supported engine under the new architecture.
   - For current planning purposes, the OpenClaw side of this baseline is interpreted against the post-1181 runtime, which already includes isolated execution routing and deterministic explicit model selection.
   - Remaining baseline concern is therefore not whether OpenClaw can support the contract in principle, but whether the new generic registry preserves that now-validated behavior.
4. **Codex Conformance Phase**
   - Add Codex as the third public conformance case under the same contract.
   - Codex onboarding is evidence that the abstraction is generic, not the justification for destabilizing existing engines.
   - Codex acceptance requires three layers of evidence:
     1. contract conformance under the normalized registry,
     2. smoke validation through a real but controlled SDLC role flow,
     3. at least one controlled full-chain SDLC validation proving planner / coder / reviewer / verifier-or-UAT continuity under the unified runtime.
5. **Post-Migration Tightening Phase**
   - After the shared architecture is proven stable, remaining provider-specific legacy branches may be removed.

Any implementation plan that skips the mandatory OpenClaw and Gemini regression baselines is non-compliant with this PRD.

### 3.15 Test Architecture and Regression Strategy
This refactor is large enough that testing must be treated as part of the architecture, not as cleanup work after coding.

The required testing model is four layers:

1. **Contract Tests**
   - Validate the engine registry schema, precedence, role gating, continuity rules, and model-resolution rules without depending on provider name.

2. **Engine Conformance Matrix**
   - Run the same engine-contract assertions against three public fixtures:
     - `openclaw`
     - `gemini`
     - `codex`
   - These tests prove all three engines satisfy the same normalized contract while still allowing different handle-acquisition strategies.

3. **Smoke Validation**
   - Run at least one real but controlled SDLC smoke flow for each required baseline or onboarding target.
   - For Codex, this must be stronger than command availability and stronger than a pure mock. It must prove that a live role flow can launch, acquire or reuse the correct native handle, and complete under the unified engine contract.

4. **Pipeline-Preservation E2E**
   - Run mocked E2E scenarios to prove SDLC control-plane behavior is preserved after the refactor.
   - The primary regression goal is not provider-specific success, but preservation of orchestrator behavior under the new provider-agnostic engine contract.

Control-plane invariants that must remain stable include:
- PR state transitions
- green-path close behavior
- red-path block and slice behavior
- coder revision-loop routing
- teardown and escalation behavior
- fail-fast notification paths

Engine-specific differences are allowed only in the data plane, such as:
- handle acquisition mechanism
- command rendering
- resume invocation shape
- model-flag rendering

### 3.16 Files Authorized for Change
This PRD authorizes work in:
- `scripts/agent_driver.py`
- `scripts/config.py`
- `scripts/orchestrator.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_arbitrator.py`
- `scripts/doctor.py`
- `config/sdlc_config.json.template`
- tests covering engine config parsing, capability gating, handle acquisition, contract conformance, and pipeline-preservation E2E

## 4. Acceptance Criteria (BDD 黑盒验收标准)
The following scenarios define the required target-state black-box acceptance criteria for the implementation produced under this PRD. They are not a claim that the current codebase already satisfies every scenario today.

- **Scenario 1: Valid external engine selection renders from config into a normalized runtime behavior**
  - **Given** `config/sdlc_config.json` defines a valid engine entry
  - **When** a compatible SDLC role selects that engine
  - **Then** the runtime launches using the command and arguments implied by the configured engine contract
  - **And** the observable runtime behavior matches the contract regardless of which public example engine is selected

- **Scenario 2: The same engine contract works across the initial conformance matrix**
  - **Given** the runtime config includes the `openclaw`, `gemini`, and `codex` engine entries defined in Section 7
  - **When** contract-conformance tests are run against each engine fixture
  - **Then** each engine is resolved through the configured engine selection contract
  - **And** each engine satisfies the same normalized start / resume contract after applying its declared handle-acquisition strategy

- **Scenario 3: Gemini coder loop uses one-time deterministic bootstrap, not per-turn rediscovery**
  - **Given** `gemini` declares `continuity_mode = stateful` and `handle_acquisition_strategy = deterministic_post_start_discovery`
  - **When** a fresh `coder` logical session is started on an isolated worktree / project context
  - **Then** SDLC acquires the Gemini native session id exactly once via provider-native session-set diff
  - **And** persists that handle
  - **And** all later turns use `-r <native_handle>` instead of repeating discovery

- **Scenario 4: Stateful Codex coder loop uses emitted native handle correctly**
  - **Given** `codex` declares `continuity_mode = stateful` and `handle_acquisition_strategy = emitted_handle_on_start`
  - **When** a fresh `coder` logical session is started
  - **Then** SDLC captures `thread.started.thread_id` from structured output
  - **And** uses that stored handle for later `codex exec resume` turns
  - **And** this proves contract compatibility only, not automatic production rollout for Codex as the default coder engine

- **Scenario 5: Stateless engines are blocked for coder**
  - **Given** an engine declares `continuity_mode = stateless`
  - **When** the runtime attempts to bind `coder` to that engine
  - **Then** the process fails before agent invocation
  - **And** it emits the exact `engine_role_continuity_error` string from Section 7

- **Scenario 6: Invalid or missing engine spec fails before execution**
  - **Given** the selected engine is missing a required field such as `kind`, `start.prompt_style`, or `handle_acquisition_strategy`
  - **When** the runtime loads config
  - **Then** the process aborts before spawning any sub-agent
  - **And** it emits the exact `engine_config_invalid` string from Section 7

- **Scenario 7: Missing executable fails clearly**
  - **Given** an engine is selected but its configured executable is not available
  - **When** SDLC performs `availability_check`
  - **Then** the process aborts before invoking the role
  - **And** it emits the exact `engine_command_missing` string from Section 7

- **Scenario 8: Role override works deterministically**
  - **Given** `default_engine` is `gemini` and `role_overrides.auditor` is `codex`
  - **When** the auditor is spawned without an explicit CLI engine override
  - **Then** the auditor uses `codex`
  - **And** other roles continue using `gemini` unless separately overridden

- **Scenario 9: `--model auto` behaves per-engine, not universally**
  - **Given** `--model auto` is passed
  - **When** the selected engine is `openclaw`
  - **Then** SDLC omits the model flag entirely
  - **When** the selected engine is `gemini` or `codex`
  - **Then** SDLC resolves `auto` to the engine’s `default_model` and passes it via the configured model arg

- **Scenario 10: Explicit OpenClaw model selection remains deterministic after registry migration**
  - **Given** an OpenClaw-backed role is launched with an explicit non-`auto` `--model` value
  - **When** the unified engine registry resolves the `openclaw` engine path
  - **Then** the launched runtime identity must match the requested explicit model or fail before work begins
  - **And** SDLC must not silently reuse a stale OpenClaw runtime binding for a different model

- **Scenario 11: Native-handle mappings are isolated and cleaned up correctly**
  - **Given** a stateful engine has acquired and persisted a native handle for a logical session
  - **When** the related PR loop is superseded, withdrawn, or fatally torn down
  - **Then** the stale mapping is not reused by future logical sessions
  - **And** another PR / role loop cannot accidentally continue the old provider session

- **Scenario 12: Pipeline-preservation behavior remains stable under multiple engine configs**
  - **Given** the orchestrator green-path and red-path mocked E2E suites exist
  - **When** those suites are run against at least the `openclaw` and `gemini` engine configs, and against `codex` where the role contract permits
  - **Then** SDLC control-plane behavior remains unchanged
  - **And** differences are limited to engine-specific command rendering and native-handle acquisition details

- **Scenario 13: Codex onboarding requires controlled smoke and full-chain proof, not command availability alone**
  - **Given** Codex has passed config validation and contract-conformance checks
  - **When** Codex is evaluated for supported-engine acceptance under this PRD
  - **Then** it must also pass at least one controlled live smoke flow
  - **And** it must pass at least one controlled full-chain SDLC validation under the unified runtime
  - **And** successful `codex --help` or isolated command invocation alone is insufficient for acceptance

- **Scenario 14: Private engine onboarding remains externalized from tracked public artifacts**
  - **Given** a private engine is defined only in local runtime `config/sdlc_config.json`
  - **When** SDLC is launched with that runtime overlay present
  - **Then** the private engine can be resolved and used through the same normalized contract
  - **And** no change to tracked public example config is required for that private engine to exist at runtime

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risks
- Reintroducing product-specific hard-coded branching after claiming to be config-driven
- Allowing a role / continuity mismatch to slip into runtime execution
- Regressing the now-validated OpenClaw baseline, especially isolated execution routing or deterministic explicit model selection
- Breaking existing OpenClaw and Gemini behavior while adding the engine registry
- Breaking coder continuity by treating native-handle acquisition as an afterthought
- Leaking private engine details into tracked source
- Making `auto` model resolution inconsistent across roles and engines
- Accepting Codex onboarding on the basis of command availability or thin smoke alone without proving revision-loop continuity and controlled full-chain stability

### Required Verification Strategy
1. **Schema Validation Unit Tests**
   - Validate missing required keys
   - Validate invalid enum values for `kind`, `continuity_mode`, `handle_acquisition_strategy`, and `auto_model_behavior`
   - Validate malformed `allowed_roles`, `availability_check`, `start`, `resume`, and `handle_capture` fields
   - Validate invalid merge outcomes produced by template + runtime overlay application

2. **Engine Resolution Unit Tests**
   - Validate precedence across explicit override, `role_overrides`, `default_engine`, env fallback, and code default
   - Validate that silent fallback is impossible
   - Validate that explicit OpenClaw non-`auto` model requests cannot silently land on a stale incompatible runtime binding

3. **Configuration Merge Contract Tests**
   - Validate top-level object merge behavior
   - Validate `role_overrides` key-based overlay behavior
   - Validate `engines` key-based overlay behavior for both existing engine override and private engine injection
   - Validate array replacement behavior
   - Validate that `null` does not act as an implicit deletion primitive

4. **Capability Gate Unit Tests**
   - Validate `stateless` rejection for `coder`
   - Validate allowed stateless roles for `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator`
   - Validate illegal combinations between `continuity_mode` and `handle_acquisition_strategy`

5. **Contract-Conformance Unit Tests**
   - Run the same normalized contract assertions against the initial engine matrix:
     - `openclaw`
     - `gemini`
     - `codex`
   - Validate that provider-specific details are expressed only through config and adapter strategy, not through control-plane branching

6. **Command Rendering Unit Tests**
   - Validate `builtin_openclaw` rendering
   - Validate `generic_external_cli` rendering for Gemini and Codex using the config contract
   - Validate positional vs flagged prompt handling
   - Validate `--model auto` handling for `omit_flag` and `use_default_model`
   - Validate explicit-model rendering and fail-fast behavior for the OpenClaw path

7. **Handle Acquisition Tests**
   - Mock OpenClaw caller-assigned-handle behavior
   - Mock Codex JSON event output and verify extraction of `thread.started.thread_id`
   - Mock Gemini before / after session listings and verify deterministic set-diff acquisition
   - Verify mapping persistence from `logical_session_key -> native_handle`
   - Verify resumed turns use the stored handle rather than repeating bootstrap

8. **Pipeline-Preservation Mocked E2E**
   - Reuse and extend existing orchestrator E2E suites so they can run under multiple engine configs
   - At minimum, preserve green-path, blocked_fatal, and slice-path behavior under the refactored engine architecture
   - Treat OpenClaw and Gemini as mandatory regression baselines before accepting Codex onboarding
   - Explicitly preserve the now-deployed OpenClaw deterministic model-selection behavior across the migration

9. **Selective Live Validation**
   - Perform non-blocking live checks for:
     - OpenClaw engine
     - Gemini engine
     - Codex engine
   - For Codex acceptance, live validation must include both a controlled smoke path and at least one controlled full-chain validation, not just availability probing
   - Keep live-provider validation out of default blocking CI

### Quality Goal
After this change, `leio-sdlc` must behave as a closed-contract, capability-gated multi-engine runtime. Adding a new compatible CLI should be primarily a config operation, not a business-logic rewrite. The primary regression objective is preservation of SDLC control-plane behavior under a provider-agnostic engine contract.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/config.py`
- `scripts/orchestrator.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_arbitrator.py`
- `scripts/doctor.py`
- `config/sdlc_config.json.template`
- tests for schema validation, engine resolution, capability gating, handle acquisition, contract conformance, and pipeline-preservation E2E

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Correctly recognized the need for a config-driven multi-engine runtime, but left core contracts open.
- **v2.0**: Closed the original open questions around public engine shape, minimal config DSL, continuity semantics, role gating, `auto` model behavior, precedence order, and runtime overlay validation.
- **v3.0**: Refined the architecture based on direct local validation of Codex and Gemini continuity behavior. The core correction was to separate `continuity_mode` from `handle_acquisition_strategy`.
- **v4.0**: Re-centered the PRD away from Codex-specific framing and clarified that OpenClaw, Gemini, and Codex are public conformance cases under one provider-agnostic engine contract.
- **v5.0**: Refreshed the approved PRD after post-approval OpenClaw baseline progress. This update records that isolated OpenClaw execution routing and deterministic explicit model selection are now already validated and deployed, so Codex is framed as third-engine conformance onboarding against the post-1181 baseline rather than onboarding onto an unresolved OpenClaw substrate.
- **Design pattern correction**: The architecture is explicitly framed as Control Plane / Data Plane Separation + Registry-Driven Strategy + Capability-Based Adapter Contract + Conformance Test Matrix.
- **Testing correction**: The PRD now requires contract tests, engine conformance matrix tests, smoke validation, and pipeline-preservation E2E so that the existing SDLC control plane can be proven stable before and after the engine refactor.
- **Private-boundary correction**: Public code and public schema must remain provider-agnostic enough that future private engines can be added through runtime-only config overlays.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### 7A. Exact schema contract (public core)
```text
Public core contract defines only normalized fields, enums, precedence rules, and fail-fast semantics.
Public core contract must not require future private engine ids to be added to public code.
Public example engines are examples and regression fixtures, not the architecture's identity model.
If onboarding a future private engine still requires adding a provider-specific branch or hard-coded engine id to public code, the architecture defined by this PRD must be considered failed.
```

### 7B. Exact target public example template to be produced (`config/sdlc_config.json.template`)
The current repository template does not yet implement this target engine schema. The following content defines the exact target template that the implementation under this PRD must create.
```json
{
  "default_engine": null,
  "role_overrides": {},
  "engines": {
    "openclaw": {
      "kind": "builtin_openclaw",
      "command": "openclaw",
      "availability_check": ["openclaw", "agent", "--help"],
      "allowed_roles": ["planner", "coder", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "stateful",
      "handle_acquisition_strategy": "caller_assigned_handle",
      "default_model": "auto",
      "auto_model_behavior": "omit_flag",
      "start": {
        "args": ["agent"],
        "prompt_style": "flag",
        "prompt_arg": "-m",
        "model_arg": "--model",
        "handle_style": "flag",
        "handle_arg": "--session-id"
      },
      "resume": {
        "args": ["agent"],
        "prompt_style": "flag",
        "prompt_arg": "-m",
        "model_arg": "--model",
        "handle_style": "flag",
        "handle_arg": "--session-id"
      },
      "handle_capture": {
        "strategy": "none",
        "list_args": [],
        "event_type": "",
        "event_field": "",
        "project_scoped": false
      }
    },
    "gemini": {
      "kind": "generic_external_cli",
      "command": "gemini",
      "availability_check": ["gemini", "--version"],
      "allowed_roles": ["planner", "coder", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "stateful",
      "handle_acquisition_strategy": "deterministic_post_start_discovery",
      "default_model": "gemini-3.1-pro-preview",
      "auto_model_behavior": "use_default_model",
      "start": {
        "args": ["--yolo"],
        "prompt_style": "flag",
        "prompt_arg": "-p",
        "model_arg": "--model",
        "handle_style": "none",
        "handle_arg": ""
      },
      "resume": {
        "args": ["--yolo"],
        "prompt_style": "flag",
        "prompt_arg": "-p",
        "model_arg": "--model",
        "handle_style": "flag",
        "handle_arg": "-r"
      },
      "handle_capture": {
        "strategy": "session_list_diff",
        "list_args": ["--list-sessions"],
        "event_type": "",
        "event_field": "",
        "project_scoped": true
      }
    },
    "codex": {
      "kind": "generic_external_cli",
      "command": "codex",
      "availability_check": ["codex", "--help"],
      "allowed_roles": ["planner", "coder", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "stateful",
      "handle_acquisition_strategy": "emitted_handle_on_start",
      "default_model": "gpt-5.4",
      "auto_model_behavior": "use_default_model",
      "start": {
        "args": ["exec", "--json"],
        "prompt_style": "positional",
        "prompt_arg": "",
        "model_arg": "--model",
        "handle_style": "none",
        "handle_arg": ""
      },
      "resume": {
        "args": ["exec", "resume", "{handle}", "--json"],
        "prompt_style": "positional",
        "prompt_arg": "",
        "model_arg": "--model",
        "handle_style": "embedded",
        "handle_arg": ""
      },
      "handle_capture": {
        "strategy": "json_event",
        "list_args": [],
        "event_type": "thread.started",
        "event_field": "thread_id",
        "project_scoped": false
      }
    }
  }
}
```

### Required enum values
```text
kind:
builtin_openclaw
generic_external_cli

continuity_mode:
stateful
stateless

handle_acquisition_strategy:
caller_assigned_handle
emitted_handle_on_start
deterministic_post_start_discovery
none

auto_model_behavior:
omit_flag
use_default_model

prompt_style:
flag
positional

handle_style:
flag
embedded
none

handle_capture.strategy:
none
json_event
session_list_diff
```

### Exact fail-fast messages
- **`engine_config_invalid`**
```text
[FATAL] Invalid SDLC engine config: {reason}
```

- **`engine_not_defined`**
```text
[FATAL] Engine '{engine_id}' is not defined in SDLC engine config.
```

- **`engine_command_missing`**
```text
[FATAL] Engine '{engine_id}' is configured, but command '{command}' is not available.
```

- **`engine_role_not_allowed`**
```text
[FATAL] Engine '{engine_id}' is not allowed for role '{role}'.
```

- **`engine_role_continuity_error`**
```text
[FATAL] Engine '{engine_id}' with continuity mode '{continuity_mode}' cannot be used for role '{role}'.
```

- **`engine_handle_strategy_error`**
```text
[FATAL] Engine '{engine_id}' cannot use handle acquisition strategy '{handle_acquisition_strategy}' with continuity mode '{continuity_mode}'.
```

- **`engine_handle_acquisition_error`**
```text
[FATAL] Engine '{engine_id}' failed to acquire a native session handle for logical session '{logical_session_key}'.
```

- **`engine_auto_model_missing_default_error`**
```text
[FATAL] Engine '{engine_id}' cannot resolve model 'auto' because no default_model is defined.
```

- **`engine_auto_model_invalid_default_error`**
```text
[FATAL] Engine '{engine_id}' cannot use default_model 'auto' with auto_model_behavior '{auto_model_behavior}'.
```

### Exact JSON keys that must not be renamed
```text
default_engine
role_overrides
engines
kind
command
availability_check
allowed_roles
continuity_mode
handle_acquisition_strategy
default_model
auto_model_behavior
start
resume
args
prompt_style
prompt_arg
model_arg
handle_style
handle_arg
handle_capture
strategy
list_args
event_type
event_field
project_scoped
```

### Exact nullability rule for public example template
```text
default_engine may be null in the public example template.
A null default_engine means the public baseline does not declare a production default engine.
In that case, the effective engine must be resolved by runtime overlay, then legacy fallback, then built-in code default according to the precedence contract.
```

### Exact role names that must not be renamed
```text
planner
coder
reviewer
auditor
verifier
arbitrator
```
