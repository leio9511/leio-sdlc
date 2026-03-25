status: open

# PR-001: Enforce Mandatory Workdir in Orchestrator CLI

## Goal
Enforce explicit project selection by making the `--workdir` argument mandatory in `orchestrator.py` to prevent project context leakage.

## Scope
- `scripts/orchestrator.py`
- `leio-sdlc/preflight.sh`

## Acceptance Criteria (AC)
1. Running `python3 scripts/orchestrator.py` without `--workdir` exits with a non-zero status code (CLI usage error).
2. Existing E2E tests in `leio-sdlc/preflight.sh` run successfully with `--workdir "$(pwd)"` passed.

## Anti-Patterns (尸检报告/避坑指南)
- DO NOT use shell commands to verify parser arguments. Write an explicit test for the python argparse logic.
