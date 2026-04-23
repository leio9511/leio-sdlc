---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Fix Execution-Agent Startup Context Contamination via OpenClaw Generic Isolated Execution Agent

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` currently launches execution-role agents through a local Python subprocess path that ultimately shells out to:

```text
openclaw agent --session-id <id> -m <message>
```

This transport is valuable because it is already:
- local and trusted,
- synchronous from the Orchestrator's point of view,
- compatible with the current retry / red-path / quarantine model,
- integrated into the existing `agent_driver.py` engine abstraction.

However, `ISSUE-1179` exposed a severe startup/context contamination defect in the current OpenClaw execution path.

### 1.1 Observed contamination symptoms
Recovered live transcripts from AMS SDLC runs showed first-turn Coder sessions reading or being pulled by main-workspace startup files such as:
- `SOUL.md`
- `USER.md`
- `memory/*.md`
- `organization_governance.md`
- earlier, also manager-oriented `leio-sdlc/SKILL.md`

The resulting failure mode was role drift:
- acknowledgment-only first turns,
- manager-style summaries,
- workflow narration instead of code execution,
- degraded coding reliability even when role prompts were otherwise strong.

This is a role-boundary defect, not merely a prompt-tuning problem.

### 1.2 What was experimentally validated
During investigation, multiple probe directions were tested.

#### Probe A: `sessions_spawn(runtime="subagent", lightContext=true)`
- **Result**: behaviorally effective.
- The spawned child avoided reading `SOUL.md`, `USER.md`, `memory/*.md`, and `organization_governance.md` unless explicitly instructed.
- This proved that **light-context semantics are sufficient to remove the contamination symptom**.

#### Probe B: run `openclaw agent` from an empty cwd
- **Result**: falsified.
- Even when launched from an empty temp directory, the session still resolved its workspace back to `/root/.openclaw/workspace` and still saw `SOUL.md`, `USER.md`, and related bootstrap files.
- Therefore, subprocess cwd manipulation is **not** a valid fix.

#### Probe C: use a dedicated isolated OpenClaw agent with its own workspace
- A real isolated agent was created with:
  ```text
  openclaw agents add sdlc-probe --workspace /tmp/openclaw_sdlc_probe_ws --non-interactive --model gpt
  ```
- Then invoked with:
  ```text
  openclaw agent --agent sdlc-probe --session-id <id> -m <message>
  ```
- **Result**: the startup context came from the isolated agent workspace, not from `/root/.openclaw/workspace`.
- The visible bootstrap files were the isolated agent's own workspace files rather than qbot's main workspace files.

This proves that, within the currently supported OpenClaw boundaries, **isolated agent identity + isolated workspace** is a viable local trusted way to shift execution startup context away from the contaminated main workspace.

### 1.3 What was rejected and why
Previous PRD drafts attempted to solve this defect by rewriting the OpenClaw execution path around external Gateway HTTP RPC calls to `sessions_spawn` / `sessions_send`.

That direction was correctly rejected by the Auditor because:
- it leaked high-risk session orchestration into an external Python-driven control plane,
- it violated secure control-plane segregation,
- it introduced brittle async-to-sync polling into the Orchestrator transport path,
- it over-expanded the blast radius for a startup contamination bug.

Therefore, this PRD explicitly does **not** replace the existing local `openclaw agent` transport with external Gateway HTTP orchestration.

### 1.4 Final architectural direction for this PRD
This PRD adopts a narrower and more correct solution:
- preserve the existing local trusted `openclaw agent` transport boundary,
- keep role logic in `leio-sdlc` prompts / playbooks,
- do **not** split role definitions into multiple role-specific agent personas,
- for `engine=openclaw` only, route execution through **one Generic Isolated Execution Agent** with its own isolated workspace,
- make that isolated workspace intentionally minimal and execution-safe,
- preserve Gemini and other non-OpenClaw engine paths unchanged.

The purpose of this PRD is to implement that adapter cleanly and deterministically so OpenClaw execution roles gain startup-context isolation without destabilizing the SDLC control plane.

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. The current local trusted OpenClaw transport boundary must be preserved. This PRD does **not** authorize replacing SDLC's OpenClaw execution path with external Gateway HTTP orchestration.
2. For `engine=openclaw`, execution roles must no longer run under the main qbot agent identity bound to `/root/.openclaw/workspace`.
3. For `engine=openclaw`, execution roles must instead run through exactly one Generic Isolated Execution Agent:
   - `sdlc-generic-openclaw`
4. The Generic Isolated Execution Agent must have its own isolated workspace, separate from `/root/.openclaw/workspace`.
5. The isolated GenericAgent workspace must be intentionally minimal and execution-safe. It must not contain the manager-oriented or qbot-specific startup stack that caused `ISSUE-1179`.
6. The GenericAgent bootstrap files must be treated as **execution-environment scaffolding only**, not as the source of role logic.
7. Role logic must remain in `leio-sdlc`'s role prompts / playbooks. The GenericAgent must not absorb or replace the current role-definition mechanism.
8. The GenericAgent workspace must not carry long-term user-memory or manager persona rules. In particular, it must not depend on `MEMORY.md` or `memory/*.md`.
9. Role continuity must be locked down exactly as follows for the OpenClaw engine path:
   - **Coder**: stateful, persistent conversation, stored in `.coder_session`
   - **Reviewer**: stateful, persistent conversation, stored in `.reviewer_session`
   - **Planner**: fresh one-shot execution, no persistent planner session file
   - **Verifier**: fresh one-shot execution, no persistent verifier session file
10. Follow-up routing must be locked down exactly as follows for the OpenClaw engine path:
   - **Coder** follow-up feedback and system alerts continue in the same persistent session
   - **Reviewer** follow-up system alerts continue in the same persistent session to preserve the malformed-JSON recovery flow
   - **Planner** always uses a fresh ephemeral session id per invocation
   - **Verifier** always uses a fresh ephemeral session id per invocation
11. The Orchestrator's red-path semantics must remain deterministic:
   - `.coder_session` is invalidated on Coder red-path reset
   - `.reviewer_session` is invalidated when reviewer persistence must be abandoned/reset
   - stateless roles do not require persisted session-file cleanup
12. Existing SDLC behavior must remain preserved for:
   - branch isolation guardrails,
   - coder revision-loop continuity,
   - reviewer malformed-JSON system-alert recovery,
   - planner one-shot PR generation,
   - verifier one-shot UAT evaluation,
   - orchestrator red/yellow path escalation logic.
13. `engine=gemini` and any non-OpenClaw engine path must remain behaviorally unchanged by this PRD.
14. The GenericAgent may have its own model, distinct from the `main` agent model. This PRD allows independent model binding for the isolated execution agent, but does **not** require different models per role.
15. This PRD does not authorize creating one isolated agent per role. The architecture must remain centered on one GenericAgent plus prompt-defined role behavior.
16. The GenericAgent must be lazy-created at runtime if it does not exist, using templates sourced from the installed `leio-sdlc` runtime directory.

### Non-Functional Requirements
1. The solution must reduce startup/context contamination for the OpenClaw execution path without expanding blast radius into the shared control plane.
2. The solution must remain locally trusted and synchronous from the Orchestrator's perspective.
3. The solution must be auditable: agent identity, workspace path, and role continuity rules must all be explicit.
4. The GenericAgent workspace must be reproducible from template files so drift can be reset by re-initialization.
5. The implementation must be testable with deterministic mocked tests and at least one live probe demonstrating that the OpenClaw execution role no longer inherits the main qbot workspace persona.
6. The implementation must preserve provider-agnostic control-plane boundaries by confining OpenClaw-specific logic to the OpenClaw adapter/backend branch.

### Boundaries
- **In Scope**:
  - OpenClaw adapter changes inside the existing `agent_driver.py` / spawn-script path
  - one Generic Isolated Execution Agent for OpenClaw execution roles
  - one isolated execution-safe workspace template for that GenericAgent
  - deploy-time synchronization of the workspace templates
  - lazy-creation logic in the OpenClaw adapter
  - exact continuity contracts per role
  - exact session-file persistence rules per role
  - exact red-path invalidation rules per persisted role
  - probe-backed contamination regression validation
- **Out of Scope**:
  - replacing the local trusted transport with Gateway HTTP orchestration
  - changing Gemini transport behavior
  - creating one isolated OpenClaw agent per role
  - moving role playbook semantics into role-specific agent bootstrap files
  - generic OpenClaw platform feature work such as global subagent skill filtering
  - unrelated observability fixes not strictly required for this startup-isolation change
  - broad orchestrator state-machine redesign

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Preserve the current trusted transport boundary
The existing transport boundary remains:
- `spawn_*` scripts render task strings
- `agent_driver.py` invokes the selected engine
- for OpenClaw, invocation continues to use local `openclaw agent` subprocess calls

This PRD explicitly rejects the previously attempted architecture of external Python -> Gateway HTTP -> `sessions_spawn/sessions_send` orchestration.

### 3.2 New OpenClaw adapter model: Generic Isolated Execution Agent
For `engine=openclaw`, `agent_driver.py` must route execution through one dedicated isolated OpenClaw agent id instead of the default `main` agent:
- `sdlc-generic-openclaw`

The launch command pattern becomes:
```text
openclaw agent --agent sdlc-generic-openclaw --session-id <resolved_session_id> -m <secure_msg>
```

This keeps the transport local and trusted while shifting the startup workspace boundary away from qbot's main workspace.

### 3.3 GenericAgent workspace policy
The `sdlc-generic-openclaw` workspace must contain only execution-safe bootstrap files.

Its purpose is **not** to redefine coder/reviewer/planner/verifier personalities. Its purpose is only to provide a clean startup shell that does not contaminate execution turns with main-agent persona.

The workspace may contain:
- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `TOOLS.md`
- optional supporting files strictly required for execution safety

The workspace must not contain:
- qbot main persona files copied from `/root/.openclaw/workspace`
- `MEMORY.md`
- `memory/*.md`
- manager-governance instructions
- long-term user-profile content irrelevant to execution

### 3.4 Template strategy and lazy-creation of the GenericAgent
The GenericAgent workspace must be generated from a dedicated minimal template set owned by `leio-sdlc`, following a strict three-stage lifecycle:

1. **Source-Code Template Definition**:
   A new template directory (e.g., `TEMPLATES/openclaw_execution_agent/`) must be created in the `leio-sdlc` workspace source. This directory holds the execution-safe, role-neutral `AGENTS.md` and `SOUL.md` (and any other required minimal bootstrap files).

2. **Deployment Sync**:
   The `deploy.sh` script must copy this template directory into the installed runtime environment (e.g., `$AGENT_SKILLS_DIR/leio-sdlc/TEMPLATES/...`), ensuring the templates are always physically available inside the secure runtime boundary alongside the `agent_driver.py` script.

3. **Lazy Creation at Runtime**:
   When `agent_driver.py` executes on the OpenClaw path, it must perform a lazy-creation check:
   - if the isolated agent `sdlc-generic-openclaw` does not exist (e.g., verify via `openclaw agents list` or a local lock/flag), it must be created dynamically (`openclaw agents add sdlc-generic-openclaw --non-interactive ...`).
   - immediately after creation, the driver must copy the bootstrap files from the runtime's template directory into the new agent's workspace.
   - this ensures the agent always starts with the exact execution-safe persona defined in source, overriding whatever default templates OpenClaw may inject.

The template philosophy remains:
- execution-safe,
- minimal,
- role-neutral,
- no manager persona,
- no long-term memory loading,
- no instruction to reinterpret or override runtime role prompts.

The GenericAgent bootstrap files must explicitly defer to the runtime-provided task / playbook / prompt as the source of role behavior.

### 3.5 Role-specific continuity contracts
#### Coder
- Transport: `openclaw agent --agent sdlc-generic-openclaw ...`
- Session model: persistent
- Session file: `.coder_session`
- Follow-up: same persistent session for review feedback and system alerts
- Red-path: invalidate `.coder_session`, create fresh session

#### Reviewer
- Transport: `openclaw agent --agent sdlc-generic-openclaw ...`
- Session model: persistent
- Session file: `.reviewer_session`
- Follow-up: same persistent session for malformed-JSON / system-alert recovery
- Red-path: invalidate `.reviewer_session`, create fresh session when required

#### Planner
- Transport: `openclaw agent --agent sdlc-generic-openclaw ...`
- Session model: one-shot
- Session file: none
- Follow-up: none, fresh ephemeral session id every invocation

#### Verifier
- Transport: `openclaw agent --agent sdlc-generic-openclaw ...`
- Session model: one-shot
- Session file: none
- Follow-up: none, fresh ephemeral session id every invocation

### 3.6 Exact OpenClaw adapter behavior in `agent_driver.py`
For `LLM_DRIVER=openclaw`:
1. Use the isolated agent id `sdlc-generic-openclaw`.
2. Resolve session-id semantics by role:
   - persistent roles reuse stored session ids
   - stateless roles generate fresh ephemeral session ids
3. Execute:
   ```text
   openclaw agent --agent sdlc-generic-openclaw --session-id <resolved_id> -m <secure_msg>
   ```
4. Preserve blocking, synchronous subprocess behavior.

For non-OpenClaw engines:
- preserve existing behavior unchanged.

### 3.7 Probe-backed architectural evidence
This PRD relies on these experimentally established facts:

1. **CWD isolation does not work** for `openclaw agent` in the current environment because the runtime still resolves workspace back to `/root/.openclaw/workspace`.
2. **`sessions_spawn(... lightContext=true)` behaviorally solves the contamination symptom**, proving the target semantic.
3. **Isolated OpenClaw agent identity/workspace routing is behaviorally real** and shifts startup context away from the main qbot workspace.

Therefore, within the current accepted system boundary, the correct implementation path is to use an isolated OpenClaw agent/workspace to approximate the validated light-context effect while preserving the trusted local transport chain.

### 3.8 Failure and rollback model
This PRD changes only the OpenClaw adapter path.
If the GenericAgent strategy proves invalid at runtime:
- the OpenClaw adapter branch must fail fast and visibly,
- the Orchestrator's existing non-zero-exit red-path behavior remains the rollback boundary,
- Gemini and other engines remain unaffected because their transports are not modified.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: OpenClaw execution no longer inherits qbot workspace persona**
  - **Given** `LLM_DRIVER=openclaw`
  - **When** an execution role is launched through the Generic Isolated Execution Agent
  - **Then** its startup-visible workspace context comes from the dedicated GenericAgent workspace rather than `/root/.openclaw/workspace`
  - **And** qbot-specific main-workspace persona/memory rules are not injected from the main workspace

- **Scenario 2: Role behavior still comes from playbook/prompt, not GenericAgent persona**
  - **Given** the GenericAgent workspace is role-neutral and execution-safe
  - **When** Coder and Reviewer are launched through it
  - **Then** they still behave according to the role prompt/playbook supplied by `leio-sdlc`
  - **And** the GenericAgent bootstrap does not replace or redefine those roles

- **Scenario 3: Coder continuity remains intact**
  - **Given** the Coder has an active `.coder_session`
  - **When** reviewer feedback is routed back to the Coder
  - **Then** the same coder session is reused and the yellow-path revision loop continues to function

- **Scenario 4: Reviewer malformed-JSON recovery still works**
  - **Given** the Reviewer returns malformed or missing JSON
  - **When** the Orchestrator issues a reviewer system alert / retry
  - **Then** the existing reviewer continuity path remains intact using the persisted `.reviewer_session`

- **Scenario 5: Planner remains one-shot**
  - **Given** the Planner is invoked on the OpenClaw engine path
  - **When** it generates PR contracts
  - **Then** it runs with a fresh ephemeral session id and no planner session file is persisted

- **Scenario 6: Verifier remains one-shot**
  - **Given** the Verifier is invoked on the OpenClaw engine path
  - **When** it performs UAT verification
  - **Then** it runs with a fresh ephemeral session id and no verifier session file is persisted

- **Scenario 7: Gemini path is untouched**
  - **Given** `LLM_DRIVER=gemini`
  - **When** the same SDLC flows are executed
  - **Then** the implementation follows the existing Gemini transport path without GenericAgent logic leaking into it

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
The main risk is not prompt wording. It is startup-context contamination for OpenClaw execution roles, plus possible regression of existing Coder/Reviewer continuity behavior.

### Verification Strategy
1. **Adapter unit tests (CI-safe)**
   - Verify OpenClaw adapter resolves `--agent sdlc-generic-openclaw`
   - Verify role-based session-id persistence rules
   - Verify Gemini path remains unchanged

2. **Spawn-script / orchestrator integration tests (CI-safe)**
   - Verify `.coder_session` persistence still works
   - Verify `.reviewer_session` persistence still works
   - Verify Planner/Verifier do not persist session files
   - Verify red-path invalidation semantics for persisted roles

3. **Live probe validation (required)**
   - Launch the Generic Isolated Execution Agent and confirm startup context no longer resolves to `/root/.openclaw/workspace`
   - Confirm the main-workspace contamination symptom is removed for the OpenClaw execution path

### Quality Goal
The OpenClaw execution path must gain startup-context isolation while preserving the local trusted synchronous transport boundary and without regressing existing role lifecycle semantics.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_verifier.py`
- `deploy.sh` (to sync templates)
- one GenericAgent workspace template set (`TEMPLATES/openclaw_execution_agent/`)
- any directly related tests required to validate role-agent mapping and lifecycle preservation

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0-v7.0**: Multiple drafts attempted to solve contamination by broad transport rewrites or insecure external Gateway orchestration. Auditor rejected those directions for violating provider boundaries, lifecycle determinism, and secure control-plane segregation.
- **Probe conclusion A**: `sessions_spawn(... lightContext=true)` behaviorally solves the contamination symptom but was not accepted as an external Python-driven transport boundary.
- **Probe conclusion B**: cwd isolation of `openclaw agent` was experimentally falsified in the current runtime.
- **Probe conclusion C**: isolated OpenClaw agent identity/workspace routing is behaviorally real and shifts startup context away from the main qbot workspace.
- **v8.0 direction**: preserve the existing local trusted OpenClaw transport but move execution roles onto one Generic Isolated Execution Agent with a dedicated execution-safe workspace. Keep role logic in prompt/playbook, not in role-specific agent workspaces.
- **v9.0**: Per Boss request, specified the three-stage lifecycle for GenericAgent management: Source (Templates) -> Deploy (Sync) -> Runtime (Lazy-create). This ensures the isolated execution environment is self-bootstrapping and consistent across deployments.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`openclaw_generic_agent_id`**:
```text
sdlc-generic-openclaw
```

- **`openclaw_generic_command_template`**:
```text
openclaw agent --agent sdlc-generic-openclaw --session-id <resolved_session_id> -m <secure_msg>
```

- **`role_continuity_contract`**:
```text
Coder=session persisted via .coder_session
Reviewer=session persisted via .reviewer_session
Planner=fresh ephemeral session id, no persisted planner session file
Verifier=fresh ephemeral session id, no persisted verifier session file
```

- **`lazy_creation_logic_contract`**:
```text
The OpenClaw adapter must lazy-create sdlc-generic-openclaw if missing, then immediately copy the execution-safe bootstrap files from the installed runtime TEMPLATES directory into the newly created agent's workspace.
```

- **`non_goal_statement`**:
```text
This PRD does not replace the local trusted OpenClaw CLI transport with external Gateway HTTP orchestration. It also does not create one isolated agent per role. It introduces one Generic Isolated Execution Agent for the OpenClaw engine path while keeping role behavior in leio-sdlc prompts/playbooks.
```
