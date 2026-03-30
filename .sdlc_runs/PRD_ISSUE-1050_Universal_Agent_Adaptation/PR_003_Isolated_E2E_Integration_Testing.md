status: closed

# PR-003: Isolated E2E Integration Testing

## 1. Objective
Establish an isolated integration testing script for the `agent_driver` to support parameterized execution without polluting the fast offline CI hook.

## 2. Scope (Functional & Implementation Freedom)
- Create a standalone test harness script for the Gemini driver integration.
- Ensure the script allows specifying the LLM model via an environment variable or parameter to allow cheap probe testing (e.g., `gemini-2.0-flash`).
- Ensure `preflight.sh` retains ONLY offline, syntax/linting checks without triggering real LLM network calls.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- `preflight.sh` contains ZERO real LLM network calls.
- The standalone E2E test harness script runs completely isolated from CI and allows parameterizing the active LLM driver/model.
- CI pipeline continues to run fast and token-optimized.
- Test script successfully exits without throwing uncaught errors upon successful invocation.
