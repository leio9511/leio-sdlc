---
Affected_Projects: [leio-sdlc]
Context_Workdir: <Project_Root>
---

# PRD v3.1: Environment Hardening and Configuration Decoupling

## 1. Context & Problem (业务背景与核心痛点)
The LEIO-SDLC platform relies heavily on sandboxed environment testing, configuration-driven engine invocation, and local-to-production rollouts. However, the platform currently exhibits critical environmental vulnerabilities and workspace coupling issues:
1. **Global Side-Effects (Cloudtop Conflict)**: Process cleanup commands have traditionally used global `pkill` actions, which clean up server or socket processes across the entire workstation. This causes concurrent developers on shared platforms or Cloudtops to terminate each other's active pipelines.
2. **Context Propagation Gaps**: Spawner scripts (specifically `spawn_verifier.py`) do not propagate the parsed absolute working directory (`workdir`) to downstream registry invocation drivers. This results in authorization bypass warnings and failure to verify directories properly under strict CLI registry checks.
3. **External Headless Dependencies**: E2E deployment tests require live linking to the `gemini` CLI. In headless staging or continuous integration (CI) environments, executing `gemini skills link` without user inputs or access credentials causes hanging states, timeout failures, and non-hermetic builds.
4. **Compliance Registry Violations**: When running secure, enterprise-internal pipelines, runtime python provisioning scripts automatically fallback to public PyPI registries on install failures. This poses a compliance risk by bypassing policy-controlled corporate repositories.
5. **Configuration Preservation Gaps**: Git-based state recovery mechanisms (`git clean -fd`) and staging rsync strategies aggressively purge local development overrides (specifically `config/engines.local.json`). This wipes out custom workstation-specific configurations whenever the orchestrator triggers error recovery or performs an atomic release swap.
6. **CLI Parameter-Parsing & Option Collisions**: Decoupled environment parameters, specifically execution timeouts like `print-timeout` for engine CLI runners, have historically been treated as raw CLI positional arguments or embedded within `one_shot_args`. This practice causes parsing collisions and breaks the isolation of environment variables from engine invocation signatures.

This PRD establishes the v3.1 product requirements to eliminate workspace blast radius side-effects, safely propagate spawner context, mock headless dependencies, enforce compliant fallback boundaries, safeguard custom environment overlays, and completely decouple runtime environment overrides from engine invocation parameters.

---

## 2. Requirements & User Stories (需求定义)

### FR-1: Verifier Spawner workdir Propagation (Issue #71)
* **Description**: The UAT verifier spawner script `scripts/spawn_verifier.py` must explicitly propagate the absolute `workdir` parameter to `invoke_agent()`.
* **Rationale**: DOWNSTREAM registries perform strict path verification to ensure the agent executes within an authorized sandbox directory. Ensuring explicit propagation prevents permission/registry bypass alerts.

### FR-2: Hermetic E2E Deploy Tests via gemini CLI Mock Stub (Issue #69)
* **Description**: Deployment testing must be hermetic and network-free. E2E deployment runs must intercept any system calls to the `gemini` CLI and automatically route them to a custom mock stub `tests/trap_stub_gemini.sh`.
* **Rationale**: Intercepting `gemini skills link` calls and exiting 0 ensures headless sandboxes do not hang or require terminal interaction.

### FR-3: Compliance-Safe Pip Registry Fallbacks (Issue #70 & Auditor correction)
* **Description**: Virtualenv bootstrap actions must fail closed on package installation failure unless explicit permission is granted.
* **Requirements**:
  - Config parameter `"allow_public_fallback": false` must be defined as the default at the root level of `config/engines.default.json`.
  - If a pip install fails during `scripts/provision_runtime.sh` or `scripts/dev_python.sh`:
    - If `"allow_public_fallback"` evaluates to `false`, the installation must immediately abort with a clear compliance warning.
    - If evaluated to `true` (via a local workspace overlay), the script may fallback to the public PyPI registry.
  - **Exclusion**: This policy does not apply to `pm-skill` deployments as they do not manage Python virtual environments or runtime bootstrapping.

### FR-4: Deployed Overlay Copy Bridge & Reset Safeguard (Auditor correction)
* **Description**: Custom engine profiles must survive staging pipelines and failure resets.
* **Requirements**:
  - `deploy.sh` must check for the existence of `config/engines.local.json` and copy it directly to `$TMP_DIR/config/engines.local.json` prior to provisioning, bypassing general rsync/gitignore blocks.
  - Orchestrator recovery runs must preserve workstation configs by executing hard resets with explicit exclusion parameters.

### FR-5: Workspace-Bound Process Management & Print-Timeout Environment Decoupling (Issue #66 / Auditor correction)
* **Description**: Background process termination must be bound strictly to the local workspace directory, and execution timeout behaviors must be decoupled to isolate environment variables from raw CLI signatures.
* **Requirements**:
  - **Workspace-Bound Process Management**: Background process PIDs spawned by the orchestrator must be appended to `.sdlc_runs/pids/sdlc_pids.txt`. During preflight/cleanup phases, the orchestrator must read this file, terminate only the PIDs listed, and wipe the file. Global commands like `pkill` are strictly prohibited.
  - **Print-Timeout Environment Decoupling**: The `print-timeout` flag configuration for direct command execution must be decoupled from CLI positional arguments.
    - In `config/engines.default.json`, the `"--print-timeout"`, `"3600s"` flags must not remain in `one_shot_args`. Instead, the configuration must utilize the `"env_extra"` dictionary to declare the print-timeout key-value argument directly: `"env_extra": { "print-timeout": "3600s" }`.
    - In `scripts/agent_driver.py`, during `direct_cli` command assembly, the spawner must dynamically extract the `"print-timeout"` value from `"env_extra"` and safely prepend `["--print-timeout", <value>]` directly to the assembled `cmd` list before extending it with any `one_shot_args` (like `--print`).

---

## 3. Architecture & Technical Strategy (架构设计与技术路线)
```mermaid
graph TD
    subgraph Workspace Root
        ORC[scripts/orchestrator.py]
        DEP[deploy.sh]
        DEV[scripts/dev_python.sh]
        CFG[config/engines.default.json]
        LCFG[config/engines.local.json]
        DRV[scripts/agent_driver.py]
    end

    subgraph Isolated Staging Env
        TMP[SKILLS_DIR/.tmp_leio-sdlc]
        PROV[scripts/provision_runtime.sh]
        PID[/.sdlc_runs/pids/sdlc_pids.txt]
    end

    DEP -- Copy Bridge --> TMP
    LCFG -- Overlay --> TMP
    PROV -- Reads Merged Config --> CFG
    PROV -- Reads Merged Config --> LCFG
    ORC -- Writes background process PIDs --> PID
    ORC -- Read and Reap targeted PIDs --> PID
    DRV -- Reads merged engines overlay --> LCFG
    DRV -- Extracts print-timeout & prepends CLI flags --> DRV
```
- **Registry Decoupling**: Registry engine lookups load `engines.default.json` and optionally merge `engines.local.json`. The root property `allow_public_fallback` controls fallback safety checks.
- **PID Blast Radius Isolation**: The directory `.sdlc_runs/pids/` acts as the state directory for active processes in the workspace context.
- **Sandboxed PATH Injection**: The test driver context manager copies the mock shell script into a sandboxed path prior to execution, guaranteeing no external CLI commands escape the sandbox.
- **Parameter-Parsing Hardening**: Moving options from positional CLI lists to structured `env_extra` mappings decouples environmental runtime properties from static spawner call signatures.

---

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### FR-1: Verifier Spawner workdir Propagation
* **Scenario: UAT Verifier Sandbox Propagation**
  * **Given** the UAT spawner `spawn_verifier.py` receives a `--workdir "/my/target/workdir"` command parameter
  * **When** it executes the agent invocation phase
  * **Then** it must explicitly forward `workdir="/my/target/workdir"` to the `invoke_agent()` execution call.

### FR-2: Hermetic E2E Deploy Tests via gemini CLI Mock Stub
* **Scenario: Sandboxed gemini Interception**
  * **Given** an E2E test executes inside `isolated_repo_env`
  * **When** the deployment run invokes the `gemini` CLI link routine
  * **Then** the command must be captured by the injected mock stub `gemini` located in the isolated `PATH`
  * **And** the stub must exit immediately with `0` on capturing `skills link`.

### FR-3: Compliance-Safe Pip Registry Fallbacks
* **Scenario: Pip failure with fallback forbidden**
  * **Given** the merged engine configuration has `"allow_public_fallback"` set to `false`
  * **When** a `pip install` routine fails inside `provision_runtime.sh` or `dev_python.sh`
  * **Then** the routine must log a compliance violation error
  * **And** immediately abort execution with exit code `1`.

* **Scenario: Pip failure with fallback permitted**
  * **Given** the merged engine configuration has `"allow_public_fallback"` set to `true`
  * **When** a secure registry `pip install` routine fails inside `provision_runtime.sh` or `dev_python.sh`
  * **Then** the routine must log a warning and execute a fallback package installation to public PyPI.

* **Scenario: pm-skill deployment bypass**
  * **Given** the staging tool chain deploys a `pm-skill` target
  * **When** it copies resources
  * **Then** it must bypass all virtualenv configurations and skip register fallback checks.

### FR-4: Deployed Overlay Copy Bridge & Reset Safeguard
* **Scenario: Preservation of Engine Overlay during deployment**
  * **Given** a workstation contains `config/engines.local.json`
  * **When** `deploy.sh` runs its build/staging routine
  * **Then** the staging directory must receive a copy of `config/engines.local.json` prior to the python runtime provisioning execution.

* **Scenario: Git clean recovery bypass**
  * **Given** the orchestrator runs in forensic error recovery mode
  * **When** it performs a `git clean` to restore the workspace state
  * **Then** it must execute with an explicit exclusion parameter for `config/engines.local.json`.

### FR-5: Workspace-Bound Process Management & Print-Timeout Decoupling
* **Scenario: Workspace-Bound Reaping**
  * **Given** the orchestrator spawns three background processes
  * **When** the processes are initialized
  * **Then** their Process IDs must be appended to `.sdlc_runs/pids/sdlc_pids.txt`
  * **And** when process cleanup is executed
  * **Then** only the PIDs listed in `.sdlc_runs/pids/sdlc_pids.txt` are reaped
  * **And** `.sdlc_runs/pids/sdlc_pids.txt` is completely cleared.

* **Scenario: Dynamic print-timeout prepending for direct_cli engine**
  * **Given** the `agy_direct_cli` engine specification has `"print-timeout"` configured as `"3600s"` in `"env_extra"`
  * **And** `"one_shot_args"` contains only `["--print"]`
  * **When** `_assemble_direct_cli_command` executes direct CLI command assembly
  * **Then** it must extract `"print-timeout"` from `"env_extra"`
  * **And** it must prepend `["--print-timeout", "3600s"]` directly to the CLI command arguments before extending with `"one_shot_args"`
  * **And** the final assembled command list must have `"--print-timeout"` and `"3600s"` positioned before the `--print` one-shot flag.

---

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Preflight Execution SLA (Performance Quality Metric)
The preflight pipeline must run in a fast, non-blocking cycle to guarantee high developer velocity:
- **Cloudtop Developer Workstations**: Target execution speed of **~2 minutes**.
- **Continuous Integration (CI) Runners**: Target execution speed of **~5 minutes**.

> [!IMPORTANT]
> The preflight execution target is strictly an architectural quality SLA. It must **NEVER** be hardcoded as an assertion or timeout limitation inside any unit test, ensuring tests remain robust across heterogeneous runner environments.

### Core Isolation Strategy
- **Sandbox Path**: All E2E test targets must execute inside the context manager `isolated_repo_env` to prevent workstation contamination.
- **Registry Override**: Tests must use transient configurations using unique runtime mock directories.

---

## 6. Framework Modifications (框架防篡改声明)
The Coder is authorized to modify the following files:
- `config/engines.default.json` (Set default fallback parameter, update default engine env_extra configurations)
- `scripts/spawn_verifier.py` (Propagate `workdir` context)
- `tests/deploy_test_support.py` (Inject sandboxed mock stub)
- `deploy.sh` (Staging copy bridge)
- `scripts/provision_runtime.sh` (Fallback error capture)
- `scripts/dev_python.sh` (Fallback error capture)
- `scripts/orchestrator.py` (Exclude overlay during cleanup, track local process PIDs)
- `scripts/agent_driver.py` (Dynamically extract print-timeout from env_extra and prepend arguments)

---

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

#### 1. Mock Stub `tests/trap_stub_gemini.sh` (Raw Content)
```bash
#!/usr/bin/env bash
# Mock gemini CLI stub for hermetic E2E deploy testing.
# Intercepts "skills link" subcommands and exits 0.

has_skills=false
has_link=false

for arg in "$@"; do
  if [ "$arg" = "skills" ]; then
    has_skills=true
  elif [ "$arg" = "link" ]; then
    has_link=true
  fi
done

if [ "$has_skills" = true ] && [ "$has_link" = true ]; then
  # Intercepted "skills link"
  exit 0
fi

echo "gemini mock called with: $*"
exit 0
```

#### 2. Complete, 4-Engine `config/engines.default.json`
```json
{
  "allow_public_fallback": false,
  "engines": {
    "openclaw_native": {
      "engine_id": "openclaw_native",
      "cli_alias": "openclaw",
      "display_name": "OpenClaw Native",
      "runtime_mode": "openclaw_native",
      "registration_visibility": "public",
      "continuity_mode": "stateful",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "none",
      "capability_surface": "runtime_managed"
    },
    "gemini_direct_cli": {
      "engine_id": "gemini_direct_cli",
      "cli_alias": "gemini",
      "display_name": "Gemini Direct CLI",
      "runtime_mode": "direct_cli",
      "registration_visibility": "public",
      "continuity_mode": "stateless",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "fail_closed",
      "capability_surface": "client_mediated",
      "execution": {
        "executable": "gemini",
        "one_shot_args": ["--yolo", "-p"],
        "model_arg": {"flag": "--model", "value": "{model}"},
        "workspace_arg": null,
        "permission_args": [],
        "sandbox_args": [],
        "timeout_seconds": 3600,
        "env_extra": {}
      }
    },
    "agy_direct_cli": {
      "engine_id": "agy_direct_cli",
      "cli_alias": "agy",
      "display_name": "Antigravity CLI (agy)",
      "runtime_mode": "direct_cli",
      "registration_visibility": "public",
      "continuity_mode": "stateless",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "fail_closed",
      "capability_surface": "client_mediated",
      "execution": {
        "executable": "agy",
        "one_shot_args": ["--print"],
        "model_arg": null,
        "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"},
        "permission_args": ["--dangerously-skip-permissions"],
        "sandbox_args": ["--sandbox"],
        "timeout_seconds": 3600,
        "env_extra": {
          "print-timeout": "3600s"
        },
        "default_model": null
      }
    },
    "gemini_acp_reference": {
      "engine_id": "gemini_acp_reference",
      "display_name": "Gemini ACP Reference",
      "runtime_mode": "acp",
      "registration_visibility": "public",
      "continuity_mode": "stateful",
      "handle_acquisition_strategy": "protocol_native",
      "fallback_policy": "fail_closed_until_prerequisite_ready",
      "capability_surface": "client_mediated"
    }
  }
}
```

#### 3. Git Clean Exclusion Parameters (Raw Signature in orchestrator.py)
```python
drun(["git", "clean", "-fd", "-e", "config/engines.local.json"])
drun(["git", "clean", "-fd", "-e", "config/engines.local.json"], check=False)
```

#### 4. Workspace-Local Process PID File Path
```text
.sdlc_runs/pids/sdlc_pids.txt
```

#### 5. Agent Driver Spawner Parameter Extraction (scripts/agent_driver.py)
```python
env_extra = execution.get("env_extra", {})
print_timeout_val = env_extra.get("print-timeout")
if print_timeout_val:
    cmd.extend(["--print-timeout", str(print_timeout_val)])
```

#### 6. Spawn Verifier Signature Update
```python
        result = invoke_agent(
            task_string,
            session_key=session_id,
            role="verifier",
            run_dir=run_dir,
            workdir=workdir,
            thinking=resolved_thinking
        )
```

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
This section logs historical iterations and architectural critiques of the environment isolation & configuration decoupling initiatives:

- **v1.0 Draft (Initial Proposal)**:
  - Proposed generic sandbox cleanup scripting and basic fallback configuration logic.
- **Auditor Rejection (v2.0 Review)**:
  - *catastrophic overwrite risk*: The reset routine utilized unconstrained `git clean -fd` commands, deleting vital workstation engine override configurations (`engines.local.json`) that took time to recreate.
  - *overlay staging gap*: The release script `deploy.sh` relied on generic `.gitignore` / `.release_ignore` rules during deployment swaps, preventing workspace engine overlays from actually staging to the production directory.
  - *pm-skill virtualenv pollution*: The original compliance fallback requirements mistakenly included `pm-skill` deployments, polluting light copy/deploy processes with unnecessary virtualenv constraints.
- **v3.0 Architectural Decisions**:
  - Explicit exclusion flags (`-e config/engines.local.json`) added to git cleanup processes.
  - Dedicated copy bridge introduced in `deploy.sh` specifically carrying over `engines.local.json` to the temporary staging directory before execution.
  - Explicitly decoupled `pm-skill` deployments from virtualenv/pip requirements.
  - Transitioned from global `pkill` side-effects to a workspace-local, file-bound process tracking system (`.sdlc_runs/pids/sdlc_pids.txt`).
- **v3.1 Architectural Decisions**:
  - Transitioned the print-timeout configuration from `one_shot_args` to `env_extra` to completely eliminate CLI flag-parsing parameter collisions and isolate option bindings.
