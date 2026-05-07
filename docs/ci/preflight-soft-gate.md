# Preflight soft gate acceptance and manual GitHub witness

This document is the canonical repository-local explanation of how the preflight soft gate is accepted and observed.

## Workflow contract anchor

- Workflow name: `Preflight`
- Workflow path: `.github/workflows/preflight.yml`
- Real gate command for default local and agent usage: `bash preflight.sh`
- Real gate command for GitHub CI uses report-all: `bash preflight.sh --report-all`
- Soft-gate meaning: visible and truthful status, but not yet a required merge blocker.

Phase 2 soft gate means the GitHub Actions result is visible and truthful, but not yet configured as a required merge blocker.
Do not use `continue-on-error` or any equivalent masking mechanism to convert a real preflight failure into a successful CI result.
The repository has one real gate, with default fail-fast local and agent usage and explicit report-all GitHub CI usage.
Fail-fast and report-all must execute the same repository preflight gate. They may differ only in stopping behavior and output aggregation.
If any preflight check fails, both fail-fast and report-all modes must exit non-zero. Report-all must never convert a failing preflight run into success.

## Layered acceptance model

### Layer A — local contract validation

Layer A is repository-local static and contract validation of `.github/workflows/preflight.yml`.
It verifies that the workflow file exists, declares the required `push` and `pull_request` triggers, and preserves the single repository preflight gate entrypoint.
Local contract coverage should verify that default local and agent usage stays `bash preflight.sh` while GitHub CI uses report-all via `bash preflight.sh --report-all`.
This is the primary correctness layer because it is local, repeatable, and does not depend on live GitHub access.

### Layer B — local behavior and semantics validation

Layer B is repository-local behavior and semantics validation.
It proves that the same repository preflight gate is used in both stopping modes and that success and failure propagation remain truthful:

- `bash preflight.sh` exit 0 -> CI job success
- `bash preflight.sh` non-zero exit -> CI job failure
- `bash preflight.sh --report-all` exit 0 -> CI job success
- `bash preflight.sh --report-all` non-zero exit -> CI job failure

Layer B also confirms that bootstrap steps do not replace or bypass the repository gate.

### Layer C — external GitHub witness

Layer C is an external GitHub witness.
It is a low-frequency manual verification step after SDLC completion.
Layer C confirms that GitHub Actions produces a real, visible run for the `Preflight` workflow and that the run reaches a terminal conclusion that can be observed by a maintainer or external QA operator.

## Manual witness boundary

External GitHub verification is manual and post-SDLC.
It is not part of the automated coder, reviewer, or UAT closed loop.
Do not treat live GitHub witness collection as a required step for every local implementation, review, or UAT cycle.

## Manual witness checklist

When a maintainer or external QA operator performs the manual witness verification, capture the following fields:

- workflow name
- workflow path
- trigger event
- head SHA
- run URL or run id
- terminal conclusion
- timestamp

Recommended concrete values for this repository:

- workflow name: `Preflight`
- workflow path: `.github/workflows/preflight.yml`
- trigger event: `push` or `pull_request`
- head SHA: the commit under verification
- run URL or run id: the GitHub Actions run reference
- terminal conclusion: `success`, `failure`, or other GitHub-visible terminal conclusion
- timestamp: when the witness was captured

## Practical handoff guidance

Complete Layers A and B inside the repository first.
After SDLC is complete, hand Layer C to a maintainer or external QA operator for one manual GitHub witness run.
A truthful red result is still useful in Phase 2 because the soft gate is meant to expose clean-runner debt rather than hide it.
