# OpenClaw CLI Compatibility Audit

This document records the findings of the bounded compatibility audit performed across existing OpenClaw CLI call sites in `leio-sdlc`.

## 1. Audit Summary

| Call Site | Command | Classification | Notes |
|-----------|---------|----------------|-------|
| `scripts/agent_driver.py` | `openclaw agents list` | **confirmed valid** | Corrected to handle human-readable card format and parse model info. |
| `scripts/agent_driver.py` | `openclaw agents add` | **confirmed valid** | Uses `--non-interactive`, `--model`, and `--workspace`. |
| `scripts/agent_driver.py` | `openclaw agent` | **confirmed valid** | Uses `--agent`, `--session-id`, and `-m`. |
| `scripts/agent_driver.py` | `openclaw agents show` | **confirmed broken** | Command does not exist in current CLI. Removed. |
| `scripts/agent_driver.py` | `openclaw message send` | **confirmed valid** | Legacy path, uses `--channel`, `-t`, and `-m`. |
| `deploy.sh` | `openclaw gateway restart` | **confirmed valid** | Verified via `openclaw gateway --help`. |
| `scripts/utils_notification.py` | `openclaw message send` | **confirmed valid** | Used in `OpenClawBridgeProvider`. |

## 2. Concrete Broken Assumptions Discovered

### 2.1 One-id-per-line `agents list` output
- **Discovery**: `scripts/agent_driver.py` assumed `openclaw agents list` returns raw IDs, one per line.
- **Reality**: Current CLI returns a human-readable card format where each agent's block starts with `- <agent_id>`.
- **Fix**: Updated `openclaw_agent_exists` to parse for `- <agent_id>`.

### 2.2 Existence of `agents show`
- **Discovery**: `scripts/agent_driver.py` relied on `openclaw agents show <agent_id>` to fetch agent metadata (specifically the model).
- **Reality**: `agents show` is not a subcommand in the current CLI.
- **Fix**: Redesigned `validate_openclaw_agent_model` to extract the agent's block from `openclaw agents list` and parse the `Model:` field.

## 3. Test Hardening

The following tests were upgraded to reflect the real CLI contract:
- `tests/test_079_agent_driver_openclaw_lazy_create.py`: Updated mocks to card format, removed `agents show` assertions, added unit test for multi-line parsing.
- `tests/test_083_openclaw_model_aware_routing.py`: Updated mocks and removed `agents show` assertions.
- `tests/test_084_openclaw_model_mismatch_guardrail.py`: Updated mocks and removed `agents show` assertions.

A new real-CLI smoke test has been added to verify core OpenClaw CLI compatibility without LLM dependence:
- `tests/test_openclaw_cli_smoke.py`
