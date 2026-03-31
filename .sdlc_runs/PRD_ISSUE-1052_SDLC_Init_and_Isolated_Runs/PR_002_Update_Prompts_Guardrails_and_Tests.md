status: in_progress

# PR-002: Update Prompts, Guardrails, and Tests

## 1. Objective
Align prompts, configuration, guardrails, and End-to-End (E2E) tests with the new `.sdlc_runs/<PR_Name>` artifact structure.

## 2. Scope (Functional & Implementation Freedom)
Modify AI agent prompts, system configurations (e.g., config/prompts.json, scripts/handoff_prompter.py), and `.sdlc_guardrail` logic to reference the dynamic, nested location of `Review_Report.md` and other artifacts. Update all associated E2E bash and Python tests to mock and assert artifacts in their new `.sdlc_runs/` locations.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
1. The AI prompts and configuration files must correctly point to the isolated artifact directory.
2. The guardrail mechanisms must protect the `.sdlc_runs/` directory from malicious modification instead of the root-level `Review_Report.md`.
3. The Coder MUST update the E2E test suite to verify the new paths and ensure the full suite passes successfully (GREEN) before submitting.