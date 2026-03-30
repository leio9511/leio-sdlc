status: open

# PR-002: Triad Scripts Integration

## 1. Objective
Refactor existing AI orchestration and spawn scripts to decouple from the hardcoded Anthropics Claude driver and integrate the new `agent_driver` abstraction.

## 2. Scope (Functional & Implementation Freedom)
- Refactor the SDLC triad script chain (Planner, Coder, Reviewer, Manager, Arbitrator, Orchestrator, PM, Handoff Prompter) to use the new `agent_driver`.
- Fetch agent prompts dynamically from the new centralized `prompts.json` config instead of using hardcoded prompts.
- Preserve all existing CI hook constraints (e.g., token-optimized pipeline execution).
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- Unit tests verify that the triad scripts successfully inject their payload into the `agent_driver`.
- Unit tests verify the triad scripts can successfully read from `prompts.json` based on their role.
- Existing core capabilities are un-affected by the integration.
- Tests must be 100% green before submission.
