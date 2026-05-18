# Issue 57 Python Execution Contract

This document is the current official operator/developer reference for Issue #57: Controlled Python Execution and Runtime Contract.

## Core goal

Define a controlled, repeatable Python execution contract for local development, testing, deployed skill runtime, and GitHub CI without depending on unmanaged system Python state.

## Scope

This contract applies to leio-sdlc local development, testing, deployed runtime execution, and GitHub CI only.

It explicitly does not define or broaden into ClawHub installation, public packaging/distribution contract, and cross-skill global runtime unification. Issue #57 is not the final install or distribution solution for leio-sdlc.

## Contract-critical Python surfaces

Issue #57 controls formal development/test entrypoints, deploy/runtime launch paths, GitHub CI default paths, and execution-contract-related smoke/tests.

Those contract-critical surfaces must not keep ambient bare `python3` execution as their official contract. They must use the controlled development/test `.venv`, the deployed runtime `.venv`, or an explicitly documented wrapper that resolves to the appropriate interpreter. Issue #59 does not exempt these surfaces.

## Noncritical `python3` residual debt

Residual `python3` references in historical docs, archived PRDs, generated `.dist`, templates/reference materials, and non-default mocked/e2e examples are nonblocking follow-up debt for Issue #59.

This bucket is intentionally narrow. It exists to avoid turning Issue #57 into a brittle whole-repository text purge while keeping the active contract-critical surfaces controlled. Reviewers should classify residual references by surface: if a reference is part of formal development/test entrypoints, deploy/runtime launch paths, GitHub CI default paths, or execution-contract-related smoke/tests, it belongs to Issue #57; if it is only historical docs, archived PRDs, generated `.dist`, templates/reference materials, or non-default mocked/e2e examples, it is tracked as Issue #59 cleanup debt.

## Dependency source

The single official Python dependency entry is requirements.txt at the repository root, currently serving runtime, development, and test dependencies together.

Do not create parallel dependency entrypoints for runtime, development, tests, or CI. Future Python dependencies needed by formal leio-sdlc execution paths must be added to this repository-root `requirements.txt` entry unless a later approved contract supersedes this document.

## Development/test execution context

The development/test execution context is the repository-root .venv.

Local development and test commands must land in that controlled environment through explicit entrypoints such as:

```bash
bash scripts/dev_python.sh -m pytest
bash preflight.sh --report-all
```

The formal contract is not manual shell activation. Operators and agents should not treat an ambient shell, a globally installed package, or a remembered activation step as evidence that leio-sdlc development/test execution is controlled.

## Deployed runtime execution context

The deployed runtime execution context is the deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap.

Deployed skill commands must use the deployed skill runtime interpreter (for example `${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python`) or an equivalent documented wrapper that resolves to that interpreter. The deployed runtime `.venv` is separate from the repository development `.venv`; success in one environment must not be used as a substitute for validating the other.

This is not a global shared Python environment for other skills. Other skills must not be required to inherit, share, or switch to the leio-sdlc runtime `.venv` as a side effect of this contract.

## Official smoke validation

`scripts/runtime_smoke.py` is the official minimal smoke entrypoint shared by deploy/runtime and CI.

Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation.

The smoke path exists to prove that the selected interpreter is the expected runtime interpreter, the resolved skill root is reviewable, key imports are available, and startup-path initialization works. It must not create SDLC runs, invoke the auditor, invoke the orchestrator, or perform long-running business execution as the default validation path.

For reviewability, successful smoke output includes the active interpreter, expected interpreter, resolved skill root, startup path, and key imports. `--skill-root` is authoritative when provided; otherwise the smoke may derive the skill root from an expected `<skill-root>/.venv/bin/python` path or from the script path when no explicit runtime interpreter shape is available.

## CI alignment

GitHub CI must use the controlled development/test execution model: create or use the repository-root `.venv`, install from repository-root `requirements.txt`, run formal test/preflight entrypoints, and execute the official `scripts/runtime_smoke.py` smoke path. CI must not depend on unmanaged system Python package state.

## Operator summary

- Dependencies: repository-root `requirements.txt` only.
- Development/testing: repository-root .venv through `scripts/dev_python.sh` and/or `bash preflight.sh --report-all`.
- Deployed runtime: deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap.
- Smoke: `scripts/runtime_smoke.py`, shared by deploy/runtime and CI.
- Boundary: leio-sdlc local development, testing, deployed runtime execution, and GitHub CI only.
