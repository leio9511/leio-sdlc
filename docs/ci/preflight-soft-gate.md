# Preflight Soft-Gate Runbook

## Scope

This runbook documents the Phase 2 GitHub Actions preflight boundary for maintainers and reviewers. It defines what is checked locally, what GitHub Actions is expected to witness after changes are pushed, and why a truthful red run is acceptable at this phase.

## Workflow and gate

Workflow path:

```text
.github/workflows/preflight.yml
```

Real gate command:

```text
bash preflight.sh
```

Phase 2 soft gate means the GitHub Actions result is visible and truthful, but not yet configured as a required merge blocker.

Do not use continue-on-error or any equivalent masking mechanism to convert a real preflight failure into a successful CI result.

The primary correctness checks for this phase must be implemented as repository-local automated contract tests against .github/workflows/preflight.yml rather than as live GitHub-only verification.

## Success and failure mapping

```text
bash preflight.sh exit 0 -> CI job success
bash preflight.sh non-zero exit -> CI job failure
```

## Local contract-test primacy

The normal coder loop should validate the workflow contract with repository-local automated tests. Those tests should inspect `.github/workflows/preflight.yml`, confirm it calls the real gate, and confirm it does not mask failures. They must not require network access, call the GitHub API, scrape the GitHub UI, or make a live GitHub Actions run the primary local validation path.

## Low-frequency external GitHub witness checklist

After the workflow is pushed, use this low-frequency external witness only when maintainers need to confirm the remote observability surface:

- Trigger a qualifying `push` or `pull_request` event.
- Confirm GitHub Actions creates a visible run named or recognizable as `Preflight`.
- Confirm the `Preflight` run reaches a visible terminal result: `success` or `failure`.
- Confirm humans can inspect the terminal result and logs in GitHub Actions.
- Treat this as an external witness check, not as the primary local coder-loop validation.

## Truthful red is acceptable in Phase 2

An initial red GitHub run is acceptable in Phase 2 when it truthfully reflects clean-runner debt exposed by `bash preflight.sh`. The goal of this phase is accurate observability, not fake greenness or immediate true-green debt cleanup.
