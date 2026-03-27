# PRD: Orchestrator Observability & Ignition Guardrail (PRD-033)

## Context
Currently, the `leio-sdlc` orchestrator suffers from "black box" execution and silent communication failures. Users are left in the dark during the long Coder/Reviewer loops, and providing an incorrect `--channel` parameter allows the orchestrator to run without any visible feedback. This PRD addresses **ISSUE-1036** by enforcing a mandatory startup handshake and adding real-time intermediate notifications.

## Requirements

### 1. Mandatory Ignition Handshake (Failure-Fast)
- **First Action**: Before any slicing or state transitions, the Orchestrator MUST attempt to send an "Initial Handshake" message to the configured `--channel`.
- **Validation**: If the `openclaw message send` command returns a non-zero exit code (indicating an invalid routing key or network failure), the Orchestrator MUST immediately `sys.exit(1)`.
- **Actionable Error**: Print a clear error message to stderr explaining that the channel parameter is invalid and providing the expected format (e.g., `slack:CXXXXXX`).

### 2. Intermediate Execution Pulse (Respiratory Feedback)
- The Orchestrator must send Slack notifications for the following lifecycle events:
    - **Coder Spawned**: "Calling Coder for [PR_ID]..."
    - **Reviewer Spawned**: "Coder submitted changes. Reviewer is now auditing..."
    - **Review Rejected**: "❌ Reviewer rejected changes. Reason: [Summary]. Retrying..."
    - **PR Merged**: "✅ [PR_ID] successfully merged to master."
- These notifications must include the `prd_id` and `pr_id` in the context for proper formatting.

### 3. Integrated UI Formatting
- All new notifications must utilize the existing `scripts/notification_formatter.py` to ensure consistent UI (icons, bolding, links) across the channel.

## Architecture
- **Process Guard**: Implementation of a synchronous blocking check at the start of `orchestrator.py`.
- **Event Mapping**: Update `notification_formatter.py` with new event types: `sdlc_handshake`, `coder_spawned`, `reviewer_spawned`, `review_rejected`, `pr_merged`.
- **Loop Integration**: Insertion of `notify_channel()` calls within the main `while` loop of the orchestrator's FSM.

## Framework Modifications
The Coder is explicitly authorized to modify the following protected framework files:
- `scripts/orchestrator.py`
- `scripts/notification_formatter.py`

## Test Strategy
- **Ignition Failure Test**: Run orchestrator with a garbage channel string (e.g., `invalid:id`). Verify it exits with code 1 and prints the actionable error.
- **Ignition Success Test**: Run orchestrator with a valid mock channel. Verify it proceeds and sends the handshake.
- **Intermediate Pulse Test**: Mock the Coder/Reviewer responses in a controlled integration test and verify that all 4 intermediate pulse messages are "sent" (captured in mocks).

## Acceptance Criteria
- [ ] Orchestrator fails to start and provides a helpful error when the channel is misconfigured.
- [ ] A "Handshake" message appears in Slack at the very start of every successful run.
- [ ] Intermediate progress (Coder/Reviewer/Merge) is visible in real-time in the Slack channel.
- [ ] All messages follow the standard SDLC notification style.
