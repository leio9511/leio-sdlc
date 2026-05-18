# Issue #59: Noncritical Python3 Reference Cleanup Debt

## Status

Follow-up debt for Issue #57. This issue is not a blocker for Issue #57 as long as contract-critical surfaces are controlled.

## Scope

Issue #59 tracks remaining non-critical `python3` references that are outside the Issue #57 blocker scope, including:

- historical docs
- archived PRDs
- generated `.dist` artifacts
- non-default mocked/e2e examples
- templates
- reference material

These references may be cleaned up later to reduce confusion, but Issue #57 is not a whole-repository `python3` text purge.

## Boundary with Issue #57

Issue #57 remains responsible for formal development/test entrypoints, deploy/runtime launch paths, GitHub CI default paths, and execution-contract-related smoke/tests.

Issue #59 does not authorize leaving uncontrolled bare `python3` in those contract-critical surfaces. If a formal development/test entrypoint, deploy/runtime launch path, GitHub CI default path, or execution-contract-related smoke/test depends on ambient bare `python3`, it remains an Issue #57 blocker and must be fixed in the controlled execution contract.

## Distribution and cross-skill non-goals

Issue #57 is limited to leio-sdlc local development, testing, deployed runtime execution, and GitHub CI only.

Issue #57 does not solve ClawHub installation, public packaging/distribution contract, and cross-skill global runtime unification.

The `leio-sdlc` runtime `.venv` is isolated to `leio-sdlc`. It does not force `pm-skill` or other skills to inherit, share, or switch to the deployed `leio-sdlc` runtime `.venv`.
