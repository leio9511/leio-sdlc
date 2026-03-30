status: closed

# PR-001: Core Agent Driver Abstraction and Prompt Config

## 1. Objective
Implement the foundational agent_driver layer to dynamically route prompts to the correct LLM backend based on environment configuration (LLM_DRIVER), along with a centralized prompt dictionary.

## 2. Scope (Functional & Implementation Freedom)
- Create a configuration registry for role-based prompts with JIT File System API guardrails.
- Implement the core abstraction router that uses a stealth terminal channel to communicate with the openclaw CLI or other defined drivers.
- Implement dynamic path resolution with $AGENT_SKILLS_DIR fallback.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- When LLM_DRIVER=gemini, the router successfully delegates the call.
- The path fallback logic is verifiable through unit tests.
- JIT File System API Prompt guardrails are actively injected into the context.
- All tests for the core abstraction and configuration loading must pass (GREEN).
