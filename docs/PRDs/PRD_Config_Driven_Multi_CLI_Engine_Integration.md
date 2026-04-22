---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Config_Driven_Multi_CLI_Engine_Integration

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` already runs through more than one execution path, but the engine behavior is still encoded as business logic branches inside the runtime. Today the codebase has first-class knowledge of:
- OpenClaw-native agent execution
- Gemini CLI execution

A third engine, Codex CLI, now needs to be onboarded. The real architectural requirement is larger than “add Codex support.” The framework must stop accreting one-off engine branches whenever a new CLI appears.

The current hard-coded model creates four concrete risks:
1. **Engine onboarding cost scales linearly with code edits**. Every new CLI tends to require new conditional logic in `agent_driver.py` and related entrypoints.
2. **Open-source/private boundary is unstable**. Future private corporate CLIs must not require their names, arguments, or invocation details to be committed into the public repository.
3. **Continuity assumptions are under-specified**. Some engines support resumable sessions, some discover provider session ids after the first run, and some are stateless. The current design does not encode that as a contract.
4. **Role safety is ambiguous**. Not every engine is valid for every SDLC role. In particular, revision-heavy coder loops cannot silently use a stateless engine unless that behavior is explicitly authorized.

This PRD therefore fixes the architecture at a closed-contract level:
- keep OpenClaw as the built-in first-class path,
- introduce a generic config-driven external CLI engine contract,
- onboard Codex through that generic contract,
- keep private engine details in local runtime config,
- fail fast when an engine is incompatible with a role or continuity requirement.

This is a final execution-grade contract for the first implementation, not a discussion placeholder.

## 2. Requirements & User Stories (需求定义)
1. **Public Template + Local Runtime Overlay**
   - The repo must ship a public template file at `config/sdlc_config.json.template`.
   - The runtime may load a local non-template config at `config/sdlc_config.json` inside the installed skill/runtime directory.
   - Private engines may exist only in the runtime config overlay and must not be required in tracked public source.

2. **Engine Registry**
   - The system must load engines from an explicit registry under `engines`.
   - Iteration 1 must support these engine ids:
     - `openclaw`
     - `gemini`
     - `codex`
   - Future private engines may be added only if they satisfy the same engine-spec contract.

3. **Two Engine Kinds Only in Iteration 1**
   - `builtin_openclaw`
   - `generic_external_cli`
   - OpenClaw remains a built-in engine kind.
   - Gemini and Codex must both use the same `generic_external_cli` contract instead of product-specific business-logic branches.

4. **Exact Engine Spec Contract**
   - Every engine entry must define the required contract fields listed in Section 7.
   - Missing required keys, invalid enum values, or malformed arrays must fail at startup before any sub-agent is invoked.

5. **Continuity Contract Must Be Explicit**
   - Every engine must declare one `continuity_mode`:
     - `persistent_session`
     - `discovered_resume`
     - `stateless`
   - Semantics are fixed:
     - `persistent_session`: the same logical session key can be passed directly on subsequent invocations.
     - `discovered_resume`: the engine creates a provider session id after first execution; SDLC must discover and persist it before reuse.
     - `stateless`: no resume attempt is allowed, ever.

6. **Role Compatibility Must Be Explicit**
   - Every engine must declare `allowed_roles`.
   - The selected engine must be rejected if the current role is not in `allowed_roles`.
   - Iteration 1 role rules are:
     - `coder` requires `persistent_session` or `discovered_resume`.
     - `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator` may use any continuity mode if the engine explicitly allows that role.
     - `stateless` engines are forbidden for `coder` in iteration 1.

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
     3. engine `default_model`,
     4. legacy environment fallback `SDLC_MODEL`,
     5. built-in constant from `scripts/config.py`.

9. **Exact `auto` Semantics**
   - `auto` is a semantic request, not a universal literal.
   - Iteration 1 behaviors are:
     - for `openclaw`, `auto_model_behavior = "omit_flag"`, meaning SDLC does not pass a model flag and lets the OpenClaw runtime/session default decide;
     - for `gemini` and `codex`, `auto_model_behavior = "use_default_model"`, meaning SDLC resolves to the engine’s `default_model` and passes that value through the configured model arg.

10. **Codex Onboarding Scope in Iteration 1**
    - Codex must be onboarded as `generic_external_cli`.
    - In iteration 1, Codex is approved only for stateless-safe roles:
      - `planner`
      - `reviewer`
      - `auditor`
      - `verifier`
      - `arbitrator`
    - Codex must be rejected for `coder` until a resumable continuity path is explicitly introduced in a future PRD.

11. **Fail-Fast Observability**
    - Unavailable commands, invalid configs, invalid role bindings, and unsupported continuity must fail with the exact strings defined in Section 7.
    - The system must not continue with degraded behavior.

12. **Scope Restraint**
    - This PRD modifies only engine selection, config loading, capability validation, and CLI rendering contracts.
    - It does not authorize broad orchestrator state-machine redesign, skill-router redesign, or prompt-contamination remediation unrelated to engine integration.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Architectural Pattern
This is an agentic runtime routing problem. The correct pattern is:
- **Strategy Pattern** for engine invocation
- **Configuration-Driven Plugin Registry** for engine definitions
- **Capability Gating** for role and continuity safety

The anti-pattern being explicitly banned is product-specific branching such as “if engine == gemini do X, if engine == codex do Y” across business logic outside the engine registry/renderer layer.

### 3.2 Runtime Shape
Iteration 1 must standardize the engine layer into exactly two runtime paths:
1. **`builtin_openclaw`**
   - implemented as a built-in engine renderer inside `agent_driver.py`
   - preserves first-class OpenClaw-native execution
2. **`generic_external_cli`**
   - implemented as a generic renderer driven entirely by engine spec fields
   - used for Gemini, Codex, and any future private CLI that conforms to the same contract

### 3.3 Configuration Layering
The load path must be:
1. read `config/sdlc_config.json.template` from the repo/runtime as the public baseline,
2. if present, overlay `config/sdlc_config.json` from the installed runtime directory,
3. validate the merged result before any engine is selected.

The public template may contain public engines such as `openclaw`, `gemini`, and `codex`.
Private corporate engines may be added only in `config/sdlc_config.json`, not in the tracked template.

### 3.4 Required Engine Contract
Every engine entry must follow the exact JSON contract in Section 7. The required meaning of key fields is:
- `kind`: selects `builtin_openclaw` or `generic_external_cli`
- `command`: executable name or path used for availability and invocation
- `availability_check`: command array used to prove the engine exists before selection
- `allowed_roles`: authoritative allowlist for role binding
- `continuity_mode`: authoritative continuity contract
- `default_model`: engine-level fallback model
- `auto_model_behavior`: `omit_flag` or `use_default_model`
- `invoke.base_args`: args always passed on every invocation
- `invoke.prompt_arg`: arg name used to pass the prompt payload
- `invoke.model_arg`: arg name used to pass a model when a model flag is needed
- `invoke.resume_arg`: arg name used to pass a resumable session id when continuity supports it
- `session_discovery`: strategy block for engines using `discovered_resume`

### 3.5 Role Resolution
The runtime must resolve the effective engine per role using this algorithm:
1. if the active script explicitly passes an engine override for this role, use it,
2. else if `role_overrides[role]` exists in config, use it,
3. else use `default_engine`.

After that selection, SDLC must validate:
1. engine id exists,
2. engine spec passes schema validation,
3. command exists via `availability_check`,
4. role is included in `allowed_roles`,
5. continuity mode is legal for the role.

If any check fails, SDLC must stop with the exact fail-fast strings from Section 7.

### 3.6 Continuity Enforcement
Iteration 1 continuity behavior must be hard-coded at the policy level:
- `coder`
  - allowed: `persistent_session`, `discovered_resume`
  - forbidden: `stateless`
- `planner`, `reviewer`, `auditor`, `verifier`, `arbitrator`
  - allowed: whatever the engine explicitly declares in `allowed_roles`
  - `stateless` is allowed for these roles

This is intentionally conservative. It prevents the architecture from silently putting revision-critical coder loops onto a fresh-session CLI.

### 3.7 Model Resolution
The runtime must resolve the effective model with this exact algorithm:
1. if `--model <value>` is provided and `<value> != auto`, use `<value>`;
2. if `--model auto` is provided, apply engine `auto_model_behavior`;
3. else if the engine has `default_model`, use it;
4. else if legacy env `SDLC_MODEL` exists, use it;
5. else fall back to `scripts/config.py` default.

`auto_model_behavior` rules:
- `omit_flag`: do not pass a model flag to the CLI
- `use_default_model`: pass the engine’s `default_model` through `invoke.model_arg`

### 3.8 Codex in Iteration 1
Codex must be introduced as a `generic_external_cli` entry in config, not as a new hard-coded product branch.
Its iteration-1 contract is:
- `continuity_mode = "stateless"`
- `allowed_roles = ["planner", "reviewer", "auditor", "verifier", "arbitrator"]`
- not legal for `coder`

That gives the system a real third engine immediately without lying about unsupported continuity.

### 3.9 Files Authorized for Change
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
- tests covering engine config parsing, capability gating, and CLI rendering

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Valid external engine selection renders from config, not product-specific branch logic**
  - **Given** `config/sdlc_config.json` defines a valid `generic_external_cli` engine entry
  - **When** a compatible SDLC role selects that engine
  - **Then** the runtime renders the command from the configured engine spec
  - **And** it does not require a new product-specific branch outside the engine registry path

- **Scenario 2: Codex can be onboarded without a Codex-specific business-logic path**
  - **Given** the runtime config includes the `codex` engine defined in Section 7
  - **When** `auditor` or `reviewer` resolves to `codex`
  - **Then** SDLC invokes Codex through the generic external CLI renderer
  - **And** the invocation uses the configured command and argument contract

- **Scenario 3: Stateless engines are blocked for coder**
  - **Given** `codex` declares `continuity_mode = "stateless"`
  - **When** the runtime attempts to bind `coder` to `codex`
  - **Then** the process fails before agent invocation
  - **And** it emits the exact `engine_role_continuity_error` string from Section 7

- **Scenario 4: Invalid or missing engine spec fails before execution**
  - **Given** the selected engine is missing a required field such as `kind` or `invoke.prompt_arg`
  - **When** the runtime loads config
  - **Then** the process aborts before spawning any sub-agent
  - **And** it emits the exact `engine_config_invalid` string from Section 7

- **Scenario 5: Missing executable fails clearly**
  - **Given** an engine is selected but its configured executable is not available
  - **When** SDLC performs `availability_check`
  - **Then** the process aborts before invoking the role
  - **And** it emits the exact `engine_command_missing` string from Section 7

- **Scenario 6: Role override works deterministically**
  - **Given** `default_engine` is `gemini` and `role_overrides.auditor` is `codex`
  - **When** the auditor is spawned without an explicit CLI engine override
  - **Then** the auditor uses `codex`
  - **And** other roles continue using `gemini` unless separately overridden

- **Scenario 7: `--model auto` behaves per-engine, not universally**
  - **Given** `--model auto` is passed
  - **When** the selected engine is `openclaw`
  - **Then** SDLC omits the model flag entirely
  - **When** the selected engine is `gemini` or `codex`
  - **Then** SDLC resolves `auto` to the engine’s `default_model` and passes it via the configured model arg

- **Scenario 8: Private engine details remain out of tracked public source**
  - **Given** a private engine is defined only in local runtime `config/sdlc_config.json`
  - **When** the public repository is inspected
  - **Then** the private engine name and invocation args are not required in tracked source files

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risks
- Reintroducing product-specific hard-coded branching after claiming to be config-driven
- Allowing a role/continuity mismatch to slip into runtime execution
- Breaking existing OpenClaw and Gemini behavior while adding the engine registry
- Leaking private engine details into tracked source
- Making `auto` model resolution inconsistent across roles and engines

### Required Verification Strategy
1. **Schema Validation Unit Tests**
   - Validate missing required keys
   - Validate invalid enum values for `kind`, `continuity_mode`, and `auto_model_behavior`
   - Validate malformed `allowed_roles`, `availability_check`, and `invoke` fields

2. **Engine Resolution Unit Tests**
   - Validate precedence across explicit override, `role_overrides`, `default_engine`, env fallback, and code default
   - Validate that silent fallback is impossible

3. **Capability Gate Unit Tests**
   - Validate `stateless` rejection for `coder`
   - Validate allowed stateless roles for `planner`, `reviewer`, `auditor`, `verifier`, and `arbitrator`

4. **Command Rendering Unit Tests**
   - Validate `builtin_openclaw` rendering
   - Validate `generic_external_cli` rendering for Gemini and Codex using the config contract
   - Validate `--model auto` handling for `omit_flag` and `use_default_model`

5. **Mocked Integration Tests**
   - Mock CLI binaries and verify exact rendered command arrays
   - Mock session discovery for `discovered_resume`
   - Validate that runtime config overlays template defaults correctly

6. **Selective Live Validation**
   - Perform non-blocking live checks for:
     - OpenClaw engine
     - Gemini engine
     - Codex engine for stateless-safe roles
   - Keep live-provider validation out of default blocking CI

### Quality Goal
After this change, `leio-sdlc` must behave as a closed-contract, capability-gated multi-engine runtime. Adding a new compatible CLI should be primarily a config operation, not a business-logic rewrite.

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
- Tests for schema validation, engine resolution, capability gating, and command rendering

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Framed the migration direction correctly, but left the engine contract open-ended.
- **Audit Rejection (v1.0)**: Rejected because the PRD demanded new config behavior and fail-fast errors while leaving `Section 7` as `None`, and because the architecture still carried unresolved open questions around config DSL, continuity, role binding, and `auto` semantics.
- **v2.0 Revision Rationale**: Closed every open contract. Defined the exact engine registry structure, continuity enums, role compatibility rules, model resolution order, fail-fast strings, and the iteration-1 Codex boundary.
- **Trade-off Chosen**: Iteration 1 intentionally refuses stateless `coder` execution. This is a restraint decision to prevent fake support for revision-heavy loops before resumable continuity is designed.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact config template contract (`config/sdlc_config.json.template`)
```json
{
  "default_engine": "gemini",
  "role_overrides": {
    "auditor": "codex"
  },
  "engines": {
    "openclaw": {
      "kind": "builtin_openclaw",
      "command": "openclaw",
      "availability_check": ["openclaw", "agent", "--help"],
      "allowed_roles": ["planner", "coder", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "persistent_session",
      "default_model": "auto",
      "auto_model_behavior": "omit_flag",
      "invoke": {
        "base_args": ["agent"],
        "prompt_arg": "-m",
        "model_arg": "--model",
        "resume_arg": "--session-id"
      },
      "session_discovery": {
        "strategy": "none",
        "list_args": [],
        "match_field": ""
      }
    },
    "gemini": {
      "kind": "generic_external_cli",
      "command": "gemini",
      "availability_check": ["gemini", "--version"],
      "allowed_roles": ["planner", "coder", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "discovered_resume",
      "default_model": "gemini-3.1-pro-preview",
      "auto_model_behavior": "use_default_model",
      "invoke": {
        "base_args": ["--yolo"],
        "prompt_arg": "-p",
        "model_arg": "--model",
        "resume_arg": "-r"
      },
      "session_discovery": {
        "strategy": "provider_cli_json",
        "list_args": ["--list-sessions", "-o", "json"],
        "match_field": "prompt"
      }
    },
    "codex": {
      "kind": "generic_external_cli",
      "command": "codex",
      "availability_check": ["codex", "--help"],
      "allowed_roles": ["planner", "reviewer", "auditor", "verifier", "arbitrator"],
      "continuity_mode": "stateless",
      "default_model": "gpt-5.4",
      "auto_model_behavior": "use_default_model",
      "invoke": {
        "base_args": [],
        "prompt_arg": "-m",
        "model_arg": "--model",
        "resume_arg": ""
      },
      "session_discovery": {
        "strategy": "none",
        "list_args": [],
        "match_field": ""
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
persistent_session
discovered_resume
stateless

auto_model_behavior:
omit_flag
use_default_model
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

- **`engine_auto_model_error`**
```text
[FATAL] Engine '{engine_id}' cannot resolve model 'auto' because no default_model is defined.
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
default_model
auto_model_behavior
invoke
base_args
prompt_arg
model_arg
resume_arg
session_discovery
strategy
list_args
match_field
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