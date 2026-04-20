---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/.openclaw/workspace/skills/leio-sdlc
---

# PRD: UAT Automated Recovery and Auditor API Key Pool

## 1. Context & Problem (业务背景与核心痛点)
1. **ISSUE-1152 (UAT Automated Recovery):** The SDLC pipeline currently aborts entirely when UAT (User Acceptance Testing) detects missing requirements (`NEEDS_FIX` & `MISSING`), requiring manual intervention (`spawn_planner.py --slice-failed-pr`) to generate remedial PRs. This breaks the fully automated closed-loop pipeline and uses a hacky parameter (`--slice-failed-pr`) that was designed for breaking down overly complex individual PRs, not macro-level missing requirements. Furthermore, if UAT returns a system error (e.g., API timeout, malformed JSON), it risks feeding garbage back into the pipeline.
2. **ISSUE-1162 (Auditor API Key Pool):** While the main pipeline successfully utilizes API key load-balancing (via `sdlc_config.json` and session stickiness in `ISSUE-1155`), `spawn_auditor.py` is isolated and still hardcodes the system default API key, making it highly susceptible to rate-limiting and quota exhaustion.

## 2. Requirements & User Stories (需求定义)
1. **State-Machine Driven UAT Recovery:** Enhance `orchestrator.py` to seamlessly handle UAT failures by automatically routing back to the Planner, appending newly generated patch PRs to the execution queue, and resuming execution.
2. **Dedicated Recovery Interface for Planner:** Add a new parameter `--replan-uat-failures <uat_report.json>` to `spawn_planner.py`, accompanied by a specialized Recovery Prompt focused exclusively on fulfilling `MISSING` requirements without rewriting existing functionality.
3. **UAT Circuit Breaker & Finite Agentic Loop:** Implement a strict 3-tier error handling routing in `orchestrator.py` for UAT states:
   - **Business Success (`PASS`)**: Finish pipeline.
   - **Business Failure (`MISSING`)**: Trigger automatic Planner recovery. **Crucially, implement a `max_uat_recovery_attempts` limit (configurable in `sdlc_config.json`, defaulting to 5). If this limit is exceeded, trigger a Hard Stop to prevent infinite agentic loops and token exhaustion.** To accurately determine if items are missing, the orchestrator MUST parse the `verification_details` array from the `uat_report.json` (not an arbitrary "missing" field) and filter for items where `"status" == "MISSING"`.
   - **System Error (Malformed JSON, Timeout, Exception)**: Implement a 3-strike retry loop. If it still fails, perform a **Hard Stop** (Circuit Breaker), send a Slack escalation alert, freeze the workspace, and update state to `UAT_ERROR` or `UAT_BLOCKED`.
4. **Auditor Load-Balancing:** Refactor `spawn_auditor.py` to integrate the existing `assign_gemini_api_key` logic. It must read keys from `sdlc_config.json` and persist fingerprint mappings in `.sdlc_runs/.session_keys.json` to leverage session stickiness.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target Files:** `scripts/orchestrator.py`, `scripts/spawn_planner.py`, `scripts/spawn_auditor.py`.
- **Orchestrator UAT Loop (FSM Transition):** Inside the orchestrator's main flow, when UAT returns `NEEDS_FIX` with `MISSING` items, it must check the `uat_recovery_count` against `max_uat_recovery_attempts` (from `sdlc_config.json`, default 5). If within limit, transition explicitly to a new state `STATE_UAT_RECOVERY`. In this state, it calls `subprocess.run(["python3", "spawn_planner.py", "--prd-file", prd_file, "--replan-uat-failures", uat_report_path])`. Rather than implicitly mutating the active queue, it explicitly transitions back to `STATE_PLANNING_EVAL` or `STATE_EXECUTING_PRS` by formally loading the new PRs from the workspace and resetting the execution cursor, ensuring a deterministic FSM flow. If the retry limit is hit, transition to `STATE_UAT_BLOCKED` and escalate.
- **Circuit Breaker:** Wrap the UAT verification call in `orchestrator.py` with `utils_json.py` logic and a 3-strike retry loop. Raise a specific exception or set a `UAT_BLOCKED` state that breaks the main loop and triggers the Slack notification without cleaning the workspace.
- **Planner Recovery Prompt:** In `spawn_planner.py`, if `--replan-uat-failures` is provided, load a dedicated system prompt. The prompt string MUST be exactly identical to the `planner_recovery_prompt` defined in Section 7 (Hardcoded Content).
- **Auditor Key Integration (DRY Principle):** Do NOT replicate the API key assignment logic in `spawn_auditor.py`. Extract the existing key assignment logic from `orchestrator.py` and other scripts into a shared module (e.g., `scripts/utils_api_key.py`). Refactor all relevant scripts, including `spawn_auditor.py`, to import and call this shared utility to assign the sticky API key based on fingerprint mapping.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: UAT Detects Missing Requirements (Within Retries)**
  - **Given** The pipeline reaches the UAT phase, `uat_recovery_count` is below the limit, and the UAT verifier outputs `{"status": "NEEDS_FIX", "verification_details": [{"status": "MISSING", "requirement": "Log output", "evidence": "Not found"}]}`.
  - **When** `orchestrator.py` processes this result.
  - **Then** It extracts the missing items from `verification_details`, explicitly transitions to `STATE_UAT_RECOVERY`, invokes `spawn_planner.py` with `--replan-uat-failures`, increments the counter, formally loads the new patch PRs, and transitions back to execution.

- **Scenario 1B: UAT Missing Requirements (Exceeds Retries)**
  - **Given** UAT detects missing requirements but `uat_recovery_count` has reached `max_uat_recovery_attempts` (default 5).
  - **When** `orchestrator.py` evaluates the FSM state.
  - **Then** It performs a Hard Stop, transitions to `STATE_UAT_BLOCKED`, and sends an escalation alert to prevent infinite loops.

- **Scenario 2: UAT System Error Circuit Breaker**
  - **Given** The UAT verifier repeatedly times out or returns malformed, non-JSON output 3 times in a row.
  - **When** `orchestrator.py` attempts to parse the UAT result.
  - **Then** It triggers a Hard Stop, freezes the workspace, updates `STATE.md` to `UAT_ERROR`, and sends a Slack escalation alert.

- **Scenario 3: Auditor Load Balancing**
  - **Given** Multiple API keys configured in `sdlc_config.json`.
  - **When** `spawn_auditor.py` is invoked.
  - **Then** It assigns a sticky API key using fingerprint mapping stored in `.session_keys.json`, ensuring it does not fallback to the global default key.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Mocking:** The UAT Verifier response should be heavily mocked during unit/E2E testing of `orchestrator.py` to simulate all three states: `PASS`, `MISSING` (with a fake JSON report), and `System Error` (random string/Timeout).
- **Planner Testing:** `spawn_planner.py` should be tested with `--replan-uat-failures` to ensure it uses the correct alternate System Prompt and correctly parses the UAT JSON report.
- **Auditor Testing:** Verify that `spawn_auditor.py` correctly reads the API key pool and falls back gracefully if `.session_keys.json` is missing or corrupted.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_auditor.py`
- `scripts/utils_api_key.py` (New file)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Initial draft combining ISSUE-1152 and ISSUE-1162 logic.
- **Audit Rejection (v1.0)**: Rejected by Auditor due to String Determinism violation (missing Planner Recovery Prompt in Section 7) and DRY principle violation (Copy-Paste of API key assignment logic).
- **v2.0 Revision Rationale**: Moved prompt to Section 7. Mandated extraction of API key logic into `utils_api_key.py` to adhere to DRY principles.
- **Audit Rejection (v2.0)**: Rejected by Auditor due to Infinite Agentic Loop risk (no max retries for UAT recovery) and Implicit Queue Mutation (appending to queue instead of formal FSM transition).
- **v3.0 Revision Rationale**: Introduced `max_uat_recovery_attempts` config (default 5) and explicit FSM states (`STATE_UAT_RECOVERY`, `STATE_UAT_BLOCKED`) to ensure finite loops and deterministic execution.
- **v4.0 Revision Rationale**: Boss mandated rollback. Corrected the PRD design flaw where it assumed an incorrect UAT JSON schema. Ensured the BDD scenario and requirements explicitly instruct the orchestrator to parse the `verification_details` array from `uat_report.json` to extract missing items, matching the actual data contract of `spawn_verifier.py`.

---

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:
- **`uat_escalation_alert` (For orchestrator.py)**: 
```text
🚨 *SDLC Pipeline Blocked: UAT Agent 发生系统级错误（如返回格式非法/超时）。现场已冻结，请人工介入排查。排查完毕后可使用 `--resume` 恢复执行。*
```

- **`planner_recovery_prompt` (For spawn_planner.py)**:
```text
作为一个架构师，不要重新规划已有的功能。请仔细阅读 UAT 报告中标记为 MISSING 的需求，生成专门针对这些遗漏点的新 Micro-PRs（例如 PR_UAT_Fix_1.md），确保不破坏现有代码。
```
