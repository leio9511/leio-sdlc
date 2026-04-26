# OpenClaw CLI Compatibility Audit

This report documents the compatibility of `leio-sdlc` with the current OpenClaw CLI surface.

## 1. Summary of Findings

The audit identified several critical incompatibilities in the `leio-sdlc` runtime adapter and test suite due to breaking changes in the OpenClaw CLI. These have been remediated in PR-004.

| Command Surface | Status | Notes |
| :--- | :--- | :--- |
| `openclaw agents list` | **Confirmed Valid** | Output format is human-readable/multi-line. Parsing logic updated. |
| `openclaw agents show` | **Confirmed Broken** | Command does not exist in current CLI. Usage removed. |
| `openclaw agents add` | **Confirmed Valid** | Used for lazy agent creation. |
| `openclaw agent` | **Confirmed Valid** | Primary execution entry point. |
| `openclaw message send` | **Confirmed Valid** | Used for remote notifications. |
| `openclaw gateway restart` | **Confirmed Valid** | Used in deploy/rollback scripts. |

## 2. Detailed Audit per Call Site

### 2.1 Agent Management Path (`scripts/agent_driver.py`)

*   **`openclaw agents list`**:
    *   **Old Assumption**: Returned raw IDs, one per line.
    *   **Current Reality**: Returns human-readable cards with annotations (e.g., `- my-agent (default)`).
    *   **Status**: **Confirmed Broken** (now Fixed).
    *   **Remediation**: Updated `openclaw_agent_exists()` and `validate_openclaw_agent_model()` to use robust prefix matching and handle trailing annotations.

*   **`openclaw agents show <agent_id>`**:
    *   **Old Assumption**: Exists and provides agent metadata.
    *   **Current Reality**: Command is missing from the CLI.
    *   **Status**: **Confirmed Broken** (now Fixed).
    *   **Remediation**: Replaced with parsing the agent card directly from the `openclaw agents list` output in `validate_openclaw_agent_model()`.

*   **`openclaw agents add <id> --non-interactive --model <m> --workspace <w>`**:
    *   **Status**: **Confirmed Valid**. Used when an isolated agent for a specific model does not exist.

*   **`openclaw agent --agent <id> --session-id <sid> -m <msg>`**:
    *   **Status**: **Confirmed Valid**. Standard execution path for all SDLC roles.

### 2.2 Notification Path (`scripts/utils_notification.py` / `scripts/agent_driver.py`)

*   **`openclaw message send --channel <c> -t <t> -m <m>`**:
    *   **Status**: **Confirmed Valid**.
    *   **Usage**: Used by `OpenClawBridgeProvider` for delivering Slack/remote notifications.

### 2.3 Deployment / Lifecycle (`deploy.sh` / `rollback.sh`)

*   **`openclaw gateway restart`**:
    *   **Status**: **Confirmed Valid**.
    *   **Usage**: Final step in deployment to ensure the gateway picks up updated skills.

## 3. Test Strategy Hardening

The following tests were identified as relying on stale CLI contract assumptions and have been hardened:

*   `tests/test_079_agent_driver_openclaw_lazy_create.py`: Updated to include cases with annotated agent IDs.
*   `tests/test_083_openclaw_model_aware_routing.py`: (Audited) Relies on `agents list`, needs to ensure mock output matches new reality.
*   `tests/test_084_openclaw_model_mismatch_guardrail.py`: (Audited) Relies on `agents list`.

### New Guardrails Added:
*   `tests/test_agent_detection_hardening.py`: Dedicated unit tests for robust agent ID parsing with various annotation styles.

## 4. Conclusion
The OpenClaw adapter in `leio-sdlc` is now compatible with the current CLI version. Future changes should be verified against the real CLI or using the new robust parsing helpers.
