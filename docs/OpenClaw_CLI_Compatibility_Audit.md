# OpenClaw CLI Compatibility Audit

## 1. Command Surface Inspected
- `openclaw agents list`: Used for agent existence detection and model metadata lookup.
- `openclaw agents show`: Used for agent model validation (confirmed removed).
- `openclaw agents add`: Used for lazy-creating agents.
- `openclaw agent`: Core command for running agent turns.
- `openclaw message send`: Used for channel notifications (Slack, etc.).
- `openclaw gateway restart`: Used for reloading the gateway after deployment.

## 2. Call Sites and Classifications

| File | Command | Classification | Notes |
|---|---|---|---|
| `scripts/agent_driver.py` | `openclaw agents list` | confirmed broken | Output is human-readable card format. Current parser `openclaw_agent_exists` assumes raw IDs. |
| `scripts/agent_driver.py` | `openclaw agents show` | confirmed broken | Subcommand `show` does not exist in current CLI. Used in `validate_openclaw_agent_model`. |
| `scripts/agent_driver.py` | `openclaw agents add` | confirmed valid | Command exists and flags are correct. |
| `scripts/agent_driver.py` | `openclaw agent` | confirmed valid | Command and flags match current CLI. |
| `scripts/agent_driver.py` | `openclaw message send` | confirmed valid | Legacy path usage matches CLI surface. |
| `scripts/utils_notification.py` | `openclaw message send` | confirmed valid | Primary notification path. Usage is robust (only relies on return code). |
| `deploy.sh` | `openclaw gateway restart` | confirmed valid | Command exists and is used correctly as the final step. |
| `scripts/rollback.sh` | `openclaw gateway restart` | confirmed valid | Command exists and is used correctly. |
| `kit-deploy.sh` | `openclaw gateway restart` | confirmed valid | Command exists and is used correctly. |

## 3. Concrete Broken Assumptions Discovered
- **`agents list` Output Parsing**: `scripts/agent_driver.py:openclaw_agent_exists()` uses `{line.strip() for line in list_stdout.splitlines()}`. This fails because current CLI output for `agents list` is human-readable (e.g., `- sdlc-generic-openclaw-gpt` instead of raw ID).
- **`agents show` Dependency**: `scripts/agent_driver.py:validate_openclaw_agent_model()` calls `openclaw agents show <agent_id>`, which results in a `Command not found` or similar error as the subcommand was removed.
- **Test Contract Drift**: 
    - `tests/test_079_agent_driver_openclaw_lazy_create.py` mocks `agents list` as one-id-per-line and asserts `agents show` is called.
    - `tests/test_083_openclaw_model_aware_routing.py` similarly asserts `agents show` usage.
    - `tests/test_084_openclaw_model_mismatch_guardrail.py` also relies on `agents show` mocks.

## 4. Planned Remediation
- **Adapter Hardening**:
    - Update `scripts/agent_driver.py` to use a regex or flexible line parser for `openclaw agents list` to detect agent IDs in the new card format.
    - Implement a new `parse_openclaw_agent_model` strategy that extracts the `Model:` field from the card output of `openclaw agents list`, replacing the dependency on `agents show`.
- **Test Suite Update**:
    - Refactor `tests/test_079_...`, `tests/test_083_...`, and `tests/test_084_...` to use realistic multi-line human-readable `agents list` output in mocks.
    - Remove all assertions for `agents show` and replace them with `agents list` parsing assertions.
- **Smoke Testing**:
    - Add a new integration test `tests/test_086_openclaw_cli_compatibility_smoke.sh` that invokes the real installed `openclaw` CLI to verify subcommands and output formats.
