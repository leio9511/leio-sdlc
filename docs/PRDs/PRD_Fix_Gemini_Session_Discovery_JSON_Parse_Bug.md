---
Affected_Projects: leio-sdlc
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Case-1-Only Engine Support for Strong Continuity

## 1. Context & Problem (业务背景与核心痛点)

### Verified facts from live Gemini experiments
Fresh live verification established the following:

1. Gemini **can resume** when given a valid resume handle.
   - `gemini -r <session-id>` works
   - `gemini -r latest` works
2. But `gemini --list-sessions -o json` does **not** provide a trustworthy JSON inventory contract for SDLC runtime parsing.
3. More importantly, even if the output is parsed successfully as text, that still does **not** answer the harder correctness question:

> After creating a new Gemini session, how can `leio-sdlc` know with 100% certainty which provider session ID belongs to that exact invocation?

That is the real blocker.

### The real bug
The core problem is not merely output format mismatch.
The real problem is:

> `leio-sdlc` currently lacks a proven authoritative bootstrap-time session-id acquisition path for non-OpenClaw engines such as Gemini.

Without that, post-hoc matching is heuristic, not authoritative.

### Architectural consequence
`leio-sdlc` should not promise strong continuity for engines unless they satisfy a strict case-1 contract.

## 2. Product Decision (产品决策)

### Support boundary
For now, `leio-sdlc` should support **only case-1 engines** for strong-resume SDLC execution.

### Definition: case-1 engine
A **case-1 engine** is an engine that supports both:

1. **Bootstrap-time authoritative ID acquisition**
   - Phase-1 startup can obtain an authoritative resume/session/conversation identifier for the newly created session.
2. **Reliable resume by that identifier**
   - Phase-2 execution can continue from that identifier reliably.

If an engine cannot satisfy both, it is **out of current support scope** for strong continuity.

## 3. Requirements & User Stories (需求定义)

### Functional Requirements

**FR-1: Case-1-only strong continuity support**
The runtime must enforce that only case-1 engines are eligible for strong continuity / strong resume support.

**FR-2: Two-phase protocol for non-OpenClaw engines**
Non-OpenClaw engines must be evaluated through a two-phase protocol:
- **Phase 1: bootstrap** — create/establish a session and obtain an authoritative resume identifier
- **Phase 2: continue** — execute the real task using that identifier

**FR-3: Bootstrap failure is strong-continuity failure**
If Phase 1 cannot obtain an authoritative resume identifier, the engine bootstrap must be treated as failed for strong continuity.

**FR-4: No heuristic discovery as correctness foundation**
Post-hoc `--list-sessions` parsing, prompt-preview matching, "latest" guessing, time-window matching, or index-based inference must not be treated as the correctness foundation for strong continuity.

**FR-5: Compatibility shims may exist, but must be non-authoritative**
Heuristic or text-parsing strategies may remain only as:
- debugging aids,
- observability helpers,
- or explicit best-effort fallbacks,
- not as strong continuity proof.

**FR-6: Thin bootstrap**
Phase-1 bootstrap must be intentionally minimal and must not carry the real task payload.
Its sole purpose is to establish a resumable session and obtain an authoritative identifier.

**FR-7: Preserve Phase-2 task strength**
The full task prompt / execution contract must remain concentrated in Phase 2 so that bootstrap does not dilute the agent's attention or weaken task performance.

### Non-Functional Requirements

**NFR-1: Honesty over fake support**
It is preferable to explicitly declare an engine unsupported than to claim strong continuity on top of heuristics.

**NFR-2: Bounded scope**
This PRD does not redesign all engine integrations at once. It establishes a support boundary and a bootstrap protocol.

## 4. Architecture & Technical Strategy (架构设计与技术路线)

### Core principle

> Strong continuity requires authoritative bootstrap-time identity, not post-hoc guesswork.

### 4.1 Two-phase engine protocol

#### Phase 1 — Bootstrap
Purpose:
- start a minimal session,
- obtain authoritative resume identifier,
- persist it to runtime-owned state.

Required property:
- the identifier must come from an authoritative CLI/runtime source,
- not merely from model free-text output.

#### Phase 2 — Continue
Purpose:
- run the actual task using the identifier obtained in Phase 1.

Required property:
- the engine must reliably continue the same session/conversation when invoked with that identifier.

### 4.2 Runtime-owned truth vs provider-owned handle
The runtime must distinguish between:

1. **Runtime-owned identity**
   - run_id
   - session_key
   - agent_invocation_id
   - prompt_path
   - workdir
   - timestamps
   - engine/model

2. **Provider-owned resume handle**
   - provider session id
   - conversation id
   - resume token
   - index or other handle

Strong continuity is only available when the provider-owned handle is acquired authoritatively at bootstrap time.

### 4.3 Gemini implication
Gemini is the motivating case.

Current evidence does not yet prove a bootstrap-time authoritative acquisition path suitable for SDLC correctness.
Therefore Gemini should not be considered a proven case-1 engine until that protocol is demonstrated.

### 4.4 Prompt construction constraint
To avoid weakening agent performance:
- Phase 1 must be an ultra-thin bootstrap prompt
- Phase 2 must keep the real execution envelope intact
- bootstrap instructions must not pollute the real task envelope

## 5. Prompt / Envelope Risk Assessment (提示词与能力退化风险)

The main concern with two-phase execution is attention dilution.
If the real task envelope is split incorrectly, the agent may treat bootstrap meta-work as part of the task and lose focus.

### Design rule
- **Do not** embed the full task in Phase 1
- **Do not** make the real execution contract compete with bootstrap instructions
- **Do** keep Phase 1 near-empty except for the minimum session-establishment action
- **Do** preserve the full current role/task envelope in Phase 2

### Practical implication
This means the existing prompt construction path must be reviewed before implementation.
Specifically:
- how role declaration is injected,
- how execution contract is assembled,
- how prompt files are created and handed to engines,
- and whether Phase 2 can remain the first true high-attention task turn.

## 6. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Unsupported engine is rejected for strong continuity**
  - **Given** an engine that cannot produce an authoritative bootstrap-time resume identifier
  - **When** SDLC strong continuity is requested
  - **Then** the runtime rejects that engine as out of current support scope

- **Scenario 2: Bootstrap obtains authoritative identifier**
  - **Given** a case-1-capable engine
  - **When** Phase 1 bootstrap runs
  - **Then** the runtime records an authoritative resume identifier for the new session

- **Scenario 3: Continue phase resumes same session**
  - **Given** a successful bootstrap result with a valid authoritative identifier
  - **When** Phase 2 begins
  - **Then** the engine continues from that exact identifier rather than starting a fresh unrelated session

- **Scenario 4: Bootstrap failure aborts strong continuity path**
  - **Given** a non-OpenClaw engine whose bootstrap phase cannot obtain an authoritative identifier
  - **When** the runtime attempts strong continuity startup
  - **Then** the runtime treats that as strong-continuity startup failure rather than falling back to heuristic identity binding silently

- **Scenario 5: Phase 2 prompt strength is preserved**
  - **Given** a two-phase engine startup design
  - **When** the real task is executed in Phase 2
  - **Then** the full task envelope remains concentrated in Phase 2 and is not materially weakened by bootstrap instructions

## 7. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Test Strategy
1. Define a bootstrap-result contract for candidate case-1 engines.
2. Add tests for bootstrap success / failure classification.
3. Add tests ensuring heuristic discovery is not silently upgraded into strong continuity proof.
4. Review existing prompt construction to ensure Phase 2 preserves current execution strength.

### Quality Goal
The goal is not to maximize nominal engine coverage.
The goal is to ensure that any supported strong-continuity engine is supported honestly and correctly.

## 8. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- prompt / envelope assembly path as needed for a thin bootstrap phase
- relevant Gemini and engine capability tests

---

## 9. Hardcoded Content (硬编码内容)

### Exact support rule
```text
Only case-1 engines are in scope for strong continuity support.
```

### Exact case-1 definition
```text
A case-1 engine must support authoritative bootstrap-time resume-id acquisition and reliable resume by that identifier.
```
