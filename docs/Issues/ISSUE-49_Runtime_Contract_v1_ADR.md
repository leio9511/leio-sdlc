# ADR: Runtime Contract v1

Status: Proposed

Issue: #49

## Problem

The runtime registry currently lacks a minimal, explicit contract for describing runtime behavior at the orchestration boundary. As a result:

- public builtin runtimes and local/private runtimes are not cleanly separated
- continuity/resume semantics are hard to compare consistently across runtime types
- fallback behavior is easy to leave implicit
- implementation details risk leaking into shared configuration

## Goal

Define a minimal runtime decision contract that lets the orchestrator make consistent decisions about:

- whether an engine may appear in shared/public registry config
- how it should be orchestrated at a high level
- what continuity/resume guarantee it actually provides
- how it is allowed to degrade when continuity or mediation breaks

This contract is intentionally about capabilities and boundaries, not implementation internals.

## Non-goals

This v1 contract does not attempt to describe:

- command/path details
- auth env var names or credential wiring
- endpoint URLs
- adapter package/module names
- timeout/retry tuning
- model alias details
- logging/redaction specifics
- local handle-mapping internals

These belong in local registry or adapter configuration layers, not in the core runtime contract.

## Proposed v1 contract

### Required fields

```json
{
  "engine_id": "string",
  "display_name": "string",

  "registration_mode": "public_builtin | local_override_only",
  "runtime_mode": "openclaw_native | direct_cli | acp",

  "continuity_mode": "authoritative_resume | mapped_resume | degraded_resume | stateless_only",
  "resume_requires_same_runtime_state": true,

  "fallback_policy": "fail_closed | fallback_to_stateless | fallback_to_legacy_runtime | disallowed",
  "capability_surface": "runtime_managed | client_mediated | mixed | unknown",

  "orchestration_support_level": "native | compatible_with_client_layer | partial | unsupported | unknown"
}
```

### Field semantics

- `engine_id`
  - Stable logical identifier used for matching, policy, and orchestration logic.
- `display_name`
  - Human-readable label only. Not used for logic.
- `registration_mode`
  - Defines distribution and governance boundary.
  - `public_builtin`: may appear in shared/default repo config.
  - `local_override_only`: must remain local/private and not be published as shared default config.
- `runtime_mode`
  - High-level orchestration category.
  - `openclaw_native`: managed within the OpenClaw-native runtime model.
  - `direct_cli`: launched as a direct CLI/subprocess integration.
  - `acp`: integrated through ACP/protocol-style adapter flow.
- `continuity_mode`
  - Declares the strength of continuation semantics.
  - `authoritative_resume`: runtime provides a first-class, trusted resume mechanism.
  - `mapped_resume`: resume works via external/local mapping rather than purely native continuity.
  - `degraded_resume`: some continuation is possible, but semantics are weaker or lossy.
  - `stateless_only`: no meaningful resume/continuation guarantee.
- `resume_requires_same_runtime_state`
  - Whether resume depends on retained local/runtime state beyond merely possessing a handle.
- `fallback_policy`
  - What degradation is permitted when preferred continuity or mediation path fails.
  - `fail_closed`: stop and surface failure.
  - `fallback_to_stateless`: may continue without continuity guarantees.
  - `fallback_to_legacy_runtime`: may switch to older/alternate runtime path.
  - `disallowed`: no fallback permitted.
- `capability_surface`
  - Summary of where operational capabilities are actually provided.
  - `runtime_managed`: runtime natively owns most execution surfaces.
  - `client_mediated`: client/orchestrator must supply mediation layer.
  - `mixed`: split responsibility.
  - `unknown`: not yet characterized.
- `orchestration_support_level`
  - Overall summary judgment for orchestrator compatibility.
  - `native`: fully aligned with orchestrator expectations.
  - `compatible_with_client_layer`: workable with explicit mediation layer.
  - `partial`: usable with meaningful limitations.
  - `unsupported`: should not be scheduled/orchestrated in this model.
  - `unknown`: not yet evaluated.

### Optional extension fields

These are useful, but should not block v1 adoption.

```json
{
  "launch_surface": "managed_runtime | subprocess | protocol_adapter",
  "handle_acquisition_strategy": "protocol_native | session_id_returned | local_mapping | heuristic_discovery | none",
  "handle_scope": "session | conversation | turn_only | unknown",
  "file_io_surface": "runtime_managed | client_mediated | mixed | unknown",
  "terminal_execution_surface": "runtime_managed | client_mediated | unsupported | unknown"
}
```

Why optional:

- they help explain why a runtime behaves a certain way
- they are not all required for the orchestrator to make core v1 decisions
- several are closer to integration anatomy than core contract boundary

## Validation rule for future fields

A field should only become required core contract if it affects at least one of:

1. whether the runtime may enter shared/public registry config
2. orchestrator branch/control-flow decisions
3. the trust boundary of continuity/resume semantics
4. the allowed degradation/fallback behavior

If it does not affect one of those, it likely belongs outside the #49 core contract.

## Review criteria

Review this proposal against these questions:

1. Does every required field affect at least one of:
   - public/local registration policy
   - orchestrator branching
   - continuity trust boundary
   - fallback/degradation behavior
2. Does any required field leak implementation details that belong in local registry/config instead?
3. Can the contract cleanly describe all three representative classes:
   - native runtime
   - direct CLI runtime
   - private/local ACP-backed runtime
4. Would removing any required field make orchestration meaningfully less safe or less deterministic?
5. Are any optional fields actually required for control-plane decisions? If yes, promote them explicitly.

## Worked examples

See `references/runtime-contract/examples/` for representative runtime objects.
