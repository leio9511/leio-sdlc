# GitHub Preflight witness capture procedure

This procedure explains how to capture the low-frequency external GitHub Actions witness for the repository `Preflight` workflow without making live GitHub part of the normal local validation loop.

## When to capture

Capture a witness only after `.github/workflows/preflight.yml` exists on the branch being pushed or reviewed. The witness must come from a real GitHub Actions run produced by one qualifying event:

- `push`
- `pull_request`

The workflow may finish green or red. The recorded run does not need to be green: a terminal `failure` is acceptable when it truthfully reflects clean-runner execution of `bash preflight.sh`. Other visible terminal conclusions, such as `success`, `cancelled`, or another terminal conclusion shown by the GitHub UI/API, should also be recorded truthfully.

## How to find the run

Use the GitHub Actions UI, a one-off `gh` command, or a one-off GitHub API lookup to locate the qualifying workflow run. These live GitHub UI/API calls are for low-frequency witness capture only.

Do not add GitHub API, browser, network, or GitHub Actions availability checks to pytest contract tests, `bash preflight.sh`, or the normal local coder/reviewer loop. Live GitHub checks must not be part of the local loop. The local loop must remain deterministic and offline/static for the workflow contract.

## Where to record the final witness

Record the final witness in exactly:

```text
docs/ci/preflight-github-witness.md
```

Do not create that witness record until a real qualifying GitHub Actions run exists.

## Minimum metadata for the witness record

The final witness record must include at least:

- workflow name: `Preflight`
- workflow file path: `.github/workflows/preflight.yml`
- trigger event: `push` or `pull_request`
- head SHA for the run
- GitHub Actions run URL or GitHub Actions run database id
- terminal conclusion reported by GitHub, such as `success`, `failure`, `cancelled`, or another terminal conclusion visible in the GitHub UI/API
- capture date or capture timestamp
