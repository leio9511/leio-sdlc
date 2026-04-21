---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Flexible Runtime Path and Decoupled Notification Architecture (ISSUE-1166) - v7.0

## 1. Context & Problem (业务背景与核心痛点)
The `leio-sdlc` framework currently has a rigid, hardcoded dependency on the `~/.openclaw/skills` directory and the `openclaw` binary for notifications. This prevents execution in standalone Gemini CLI environments. Furthermore, startup handshakes are duplicated and lack a consistent "Fail Fast" mechanism across all notification modes, risking "message black holes" where the system continues running while the user is unaware of its state.

## 2. Requirements & User Stories (需求定义)
1. **Configurable Runtime Directory**: 
   - Introduce a `SDLC_RUNTIME_DIR` environment variable.
   - **Default Behavior**: If the variable is unset, default to `~/.openclaw/skills`.
   - **Enforcement**: Maintain the core SDLC discipline: code MUST be deployed to the runtime directory before execution.
2. **Unified & Decoupled Notification Architecture (Fail-Fast)**:
   - The `--channel` parameter remains mandatory.
   - **Route: stdout**: If `--channel stdout`, direct all status updates to the terminal.
   - **Route: remote**: If `--channel <id>`, use a generic provider-agnostic bridge.
   - **Absolute Fail-Fast**: If ANY notification (including the ignition handshake) fails to deliver to the requested channel, the system MUST immediately exit with a fatal error. Silent fallbacks or "swallowing" exceptions are strictly prohibited.
3. **Centralized Ignition Handshake**: Move the startup handshake logic into the `agent_driver` layer to ensure consistent "heartbeat" across all entry points.
4. **Environment-Agnostic Error Hints**: Dynamic JIT hints must use the active `SDLC_RUNTIME_DIR` instead of hardcoded strings. These hints must follow the exact templates defined in Section 7.
5. **Configurable Notification Tooling**: The binary name used for remote notifications (e.g., `openclaw`) must not be magic/hardcoded in logic; it must be defined as `NOTIFICATION_BRIDGE_BINARY` in `config.py`, defaulting to `openclaw`.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target Files**: `scripts/agent_driver.py`, `scripts/orchestrator.py`, `scripts/spawn_auditor.py`, `scripts/config.py`, `scripts/doctor.py`, `scripts/utils_notification.py` (New file).
- **Decoupled Notification (Strategy Pattern)**:
  - Create `scripts/utils_notification.py`.
  - Implement a base `NotificationProvider` class and two concrete implementations: `StdoutProvider` and `OpenClawBridgeProvider`.
  - Implement `NotificationRouter` to orchestrate these providers.
  - Centralize `send_ignition_handshake` in this module.
- **Runtime Discovery**:
  - In `config.py`, resolve `SDLC_RUNTIME_DIR` using the environment variable with the `~/.openclaw/skills` fallback.
- **Rollback & Safety Strategy**:
  - **Environment-Level Toggle**: Introduce `SDLC_NOTIFICATION_VERSION=2`. If set to `1`, the system will bypass the new router and use legacy code.
  - **Strict Error Handling**: Any exception in the `NotificationRouter` or its providers must be raised up to the main script, triggering a `sys.exit(1)` after logging the specific error to stderr.
- **Path Resolution**:
  - Binary/script resolution remains relative to the *deployed* runtime location.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Default OpenClaw Runtime**
  - **Given** `SDLC_RUNTIME_DIR` is not set and the `openclaw` tool is in the PATH.
  - **When** I run the orchestrator with `--channel slack:C123`.
  - **Then** the notification is successfully sent via the gateway.

- **Scenario 2: Custom Standalone Runtime with stdout**
  - **Given** `SDLC_RUNTIME_DIR` is set to a custom path and code is deployed there.
  - **When** I run the orchestrator with `--channel stdout`.
  - **Then** the system identifies the custom runtime and prints the handshake with the `[NOTIFY]` prefix to the terminal.

- **Scenario 3: Fail-Fast on Missing Bridge**
  - **Given** a remote channel is specified but the delivery tool is missing or fails.
  - **When** the pipeline attempts to initialize.
  - **Then** the system exits immediately with a fatal error message.

- **Scenario 4: Dynamic Path Hinting**
  - **Given** `SDLC_RUNTIME_DIR` is set to a custom path.
  - **When** a boundary violation occurs.
  - **Then** the system displays a JIT hint that correctly includes the absolute custom path.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Verification**: New test suite `tests/test_notification_routing.py` to mock tool failures and verify `sys.exit(1)` triggers.
- **E2E**: Verify that the help text and error messages display the dynamic runtime path.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/orchestrator.py`
- `scripts/spawn_auditor.py`
- `scripts/config.py`
- `scripts/doctor.py`
- `scripts/utils_notification.py` (New File)
- `deploy.sh`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_arbitrator.py`
- `scripts/spawn_manager.py`
- `scripts/spawn_planner.py`
- `tests/test_notification_routing.py` (New File)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v6.0 Revision Rationale**: Decoupled notification logic into `scripts/utils_notification.py`. Introduced rollback toggle.
- **Audit Rejection (v6.0)**: Rejected for 'Fail Silent' logic in Section 3 (Zero-Crash Handshake) which conflicted with the core Fail-Fast requirement.
- **v7.0 Revision Rationale**: Removed all "Zero-Crash" or exception-swallowing logic. Re-enforced strict Fail-Fast across all notification routes to prevent message black holes.

---

## 7. Hardcoded Content (硬编码内容)

### Notification Templates:
- **`sdlc_handshake`**: `🤝 [SDLC Engine] Initial Handshake successful. Channel linked.`
- **`auditor_start`**: `🚀 [Auditor] Starting PRD audit for: {prd_file}`
- **`planner_start`**: `🔪 [Planner] Slicing PRD into Micro-PRs...`
- **`planner_done`**: `✅ [Planner] Slicing complete. {count} PRs generated.`
- **`coder_start`**: `💻 [Coder] Implementing {pr_id}...`
- **`reviewer_start`**: `🔍 [Reviewer] Auditing changes for {pr_id}...`
- **`merge_success`**: `✅ [Merge] {pr_id} merged to master.`
- **`uat_start`**: `🧪 [UAT] Starting final verification...`

### Errors & JIT Hints:
- **`binary_missing_error`**: `[FATAL] Requested remote channel '{channel}' but the required message-delivery tool '{binary}' was not found in PATH.`
- **`notification_stdout_prefix`**: `[NOTIFY]`
- **`runtime_hint_template`**: `[JIT] To fix this, run: python3 {runtime_dir}/leio-sdlc/scripts/commit_state.py --files {path}`
- **`dirty_workspace_hint`**: `[JIT] To fix this, run: git stash push -m "sdlc pre-flight stash" --include-untracked`

### Configuration Defaults:
- **`default_runtime_dir`**: `~/.openclaw/skills`
- **`default_bridge_binary`**: `openclaw`
