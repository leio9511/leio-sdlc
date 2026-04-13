---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1113 & 1116 - SDLC CI Stabilization & Stateful Reviewer Self-Correction

## 1. Context & Problem (业务背景与核心痛点)
The SDLC Orchestrator pipeline currently faces two major blockers:
1. **Brittle CI Scripts**: `scripts/spawn_coder.py` lacks a `__main__` guard, breaking `pytest` collection. Various E2E scripts also contain brittle or outdated paths.
2. **Stateless Reviewer JSON Parsing (The "Red Path" Loop)**: The Reviewer's task is to analyze diffs and output a structured JSON report. Often, the LLM hallucinates Markdown blocks or conversation text alongside the JSON. Our current Regex-based parsing is brittle. When parsing fails, the Orchestrator brutally resets the Coder's progress ("Red Path"). 
**Solution Insight**: Instead of building complex JSON parsers, we should treat the Reviewer like the Coder. If the output isn't standard JSON, we simply send a `--system-alert` back to the *same* Reviewer session, forcing it to correct its own output.

## 2. Requirements & User Stories (需求定义)
1. **CI Stabilization**:
   - Guard `spawn_coder.py` with `if __name__ == "__main__":`.
   - Update `agent_driver.py` Gemini invocation to include headless flags (`--yolo`, `-p`).
2. **Stateful Reviewer Session**:
   - `spawn_reviewer.py` MUST persist and read a `.reviewer_session` file in the run directory (similar to how `spawn_coder.py` does).
   - Add a `--system-alert` flag to `spawn_reviewer.py`. If invoked with this flag, it sends the alert directly to the existing Reviewer session to ask for correction.
3. **Orchestrator Self-Correction Loop**:
   - In `orchestrator.py` (State 4), replace the immediate "Red Path" failure with a 3-attempt retry loop.
   - If `json.loads` fails on the Reviewer's output, re-invoke `spawn_reviewer.py` with a `--system-alert` instructing it to output strict JSON.
   - If it succeeds, proceed to Merge. If it fails 3 times, then trigger the Red Path reset.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Reviewer Session Lifecycle**:
  - **Init**: On attempt 1, `spawn_reviewer.py` creates a new `openclaw agent` session and saves the Session ID to `run_dir/.reviewer_session`.
  - **Correction**: On parse failure, `orchestrator.py` invokes `spawn_reviewer.py --system-alert "..."`. The script reads `.reviewer_session` and calls `openclaw agent --session-id <ID> -m <Alert>`.
  - **Cleanup**: Handled by existing SDLC cleanup scripts.
- **Parsing**: Use standard `json.loads()` after stripping optional ```json markdown blocks. Do not over-engineer the parser; rely on the LLM's self-correction.
- **Concurrency**: The `.reviewer_session` file is scoped strictly to the `run_dir` for a specific PR, ensuring no race conditions across parallel SDLC runs.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Running `pytest tests/ --collect-only` executes successfully without Python `SystemExit` errors.
- **Scenario 2**: If the Reviewer outputs invalid JSON, the orchestrator logs a warning, increments the retry counter, and the Reviewer corrects itself in the next attempt.
- **Scenario 3**: The Coder's progress is NEVER reset just because the Reviewer output bad JSON on the first try.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Add tests in `tests/test_orchestrator.py` simulating `subprocess.run` returning invalid JSON once, then valid JSON on the second attempt, ensuring the loop completes and `notify_channel` is called.
- **Smoke Testing**: Run standard E2E pipeline scripts to verify the CI stabilizes.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_coder.py`
- `scripts/agent_driver.py`
- `scripts/spawn_reviewer.py`
- `scripts/orchestrator.py`

## 7. Hardcoded Content (硬编码内容)

### Gemini CLI Headless Flags
```python
["gemini", "--yolo", "-p"]
```

### Reviewer System Alert Prompt
```text
SYSTEM ALERT: Your previous output could not be parsed as valid JSON. Please return ONLY a strict JSON object matching the required schema. No markdown formatting, no conversational text.
```