---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Atomic Refactoring of Agent Driver API (v6)

## 1. Context & Problem (业务背景与核心痛点)
The LEIO SDLC pipeline currently suffers from a critical stability issue (ISSUE-1150) where the Reviewer stage consistently fails when using the `gemini` engine. This failure stems from a deeper architectural flaw in `scripts/agent_driver.py`. 

**The Flaw**: The core `invoke_agent` function has an inconsistent and ambiguous return signature. It prints the agent's `stdout` to the console but returns only a `session_key` (a string) to the caller, *unless* a specific `return_output=True` flag is passed (in which case it returns a tuple). 
**The Consequence**: `scripts/spawn_reviewer.py` calls this function expecting the agent's JSON output (to write to an artifact file) but receives the `session_key` instead because it omits the flag. The script writes this incorrect key to `review_report.json`, causing fatal parsing errors downstream in the `orchestrator.py`.
**Why Previous Attempts Failed**: We attempted "fake compatibility" (`__str__` shims) and "interface versioning" (`_v2` functions). The Auditor rejected these as anti-patterns (Cowardly Refactoring / Primitive Obsession). They create technical debt and interface fragmentation for a core internal API.

**The Necessity of Atomic Refactoring**: We must fix the root cause—the ambiguous API—decisively. Leaving legacy API paths or using magic methods masks the fragility of the data passing. An atomic refactoring is required to establish a strong-typed, unambiguous contract between the driver and all its callers, eliminating this class of runtime errors permanently.

## 2. Requirements & User Stories (需求定义)
- **REQ-1 (Strong Typing)**: The `invoke_agent` API must return a predictable, structured, strongly-typed object containing all relevant execution data (session ID, stdout, stderr, exit codes).
- **REQ-2 (Atomic Update)**: All scripts utilizing `invoke_agent` must be updated synchronously to consume the new structured return type.
- **REQ-3 (Safety & Verification)**: The refactoring must follow best practices for safe code modification, ensuring no existing workflows (Planner, Coder, Reviewer) break due to the API contract change.
- **REQ-4 (Clean Code)**: The refactoring must eliminate technical debt (remove `return_output` flags, remove ambiguous return types).

## 3. Architecture & Technical Strategy (架构设计与技术路线)
We will execute an **Atomic Refactoring** adopting the **Result Object Pattern**. This aligns with Martin Fowler's refactoring principles: change the function signature and update all callers simultaneously within a single, atomic commit to prevent a broken intermediate state.

**Step 1: Define the Contract (Result Object)**
- Modify `scripts/agent_driver.py`.
- Introduce a dataclass `AgentResult` to encapsulate the output.
- *Rationale*: Replaces primitive obsession (returning strings/tuples) with a semantic object, improving readability and future extensibility without breaking signatures again.

**Step 2: Update the Provider (`agent_driver.py`)**
- Modify `invoke_agent` to always instantiate and return an `AgentResult`.
- Remove the `return_output` parameter entirely.

**Step 3: Update the Consumers (The `spawn_*.py` suite)**
- Atomically modify all caller scripts: `spawn_reviewer.py`, `spawn_coder.py`, `spawn_planner.py`, `spawn_arbitrator.py`, `spawn_manager.py`, `handoff_prompter.py`, and `pm.py` (if it uses it).
- *Change*: Update call sites from `var = invoke_agent(...)` to `result = invoke_agent(...)` and explicitly access `result.session_key` or `result.stdout` as required by each specific script's logic.

**Step 4: Ensuring Safety (Testing Strategy)**
To ensure this refactoring does not break functionality:
1.  **Compiler/Linter as First Line of Defense**: By changing the return type to an object, any caller we miss updating will fail immediately with an `AttributeError` (e.g., trying to use an object as a string session ID), making regressions highly visible and easy to catch locally before execution.
2.  **Comprehensive E2E Coverage**: We will rely on the existing `./preflight.sh` which exercises the full multi-agent pipeline (Planner -> Coder -> Reviewer) to guarantee that the data flow across the new API contract is intact end-to-end.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: End-to-end SDLC pipeline executes successfully with the new API contract**
  - **Given** the SDLC codebase has undergone the atomic `AgentResult` refactoring
  - **When** a user initiates a full pipeline run (`orchestrator.py`) with a valid PRD
  - **Then** the Planner must successfully generate PR slice files
  - **And** the Coder must successfully generate and commit code
  - **And** the Reviewer must successfully generate a valid `review_report.json` containing the evaluation
  - **And** the Orchestrator must successfully merge the code.

- **Scenario 2: The Reviewer artifact contains actual agent output, not session keys**
  - **Given** the Reviewer stage has completed
  - **When** the system reads `review_report.json`
  - **Then** the file content must be a valid JSON object matching the reviewer schema
  - **And** it must NOT contain the literal string format `subtask-...` representing a session key.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Core Risk**: Breaking a downstream consumer script by forgetting to update its call site to handle the new `AgentResult` object.
- **Mitigation**: 
  1. Use global search/replace or AST-aware refactoring tools (via the Coder agent) to ensure ALL instances of `invoke_agent` are updated.
  2. Rely heavily on the `tests/` directory. The unit tests for each `spawn_*.py` script MUST be updated to mock the new `AgentResult` object. If a unit test fails, the refactoring is incomplete.
  3. The final gate is the E2E test suite running locally.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_arbitrator.py`
- `scripts/spawn_manager.py`
- `scripts/handoff_prompter.py`
- `scripts/pm.py`
- `tests/*` (All test files that mock or invoke `invoke_agent`)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1-v5**: Iterated through Tuple returns, `__str__` magic methods, and `_v2` interface versioning. All rejected for introducing technical debt, primitive obsession, or cowardly refactoring anti-patterns.
- **v6**: Settled on Atomic Refactoring using a Result Object, adhering to strict software engineering refactoring principles to permanently fix the internal API contract.

---

## 7. Hardcoded Content (硬编码内容)
- **Dataclass Definition for `AgentResult`**:
```python
from dataclasses import dataclass

@dataclass
class AgentResult:
    session_key: str
    stdout: str
    stderr: str = ""
    return_code: int = 0
```