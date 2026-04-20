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
- **Orchestrator UAT Loop (FSM Transition):** Inside the orchestrator's main flow, when UAT returns `NEEDS_FIX` with `MISSING` items, it must check the `uat_recovery_count` against `max_uat_recovery_attempts` (from `sdlc_config.json`, default 5). If within limit, transition explicitly to a new state (e.g. log "State 7: UAT Recovery"). In this state, it MUST use the framework's `dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--prd-file", args.prd_file, "--replan-uat-failures", uat_out_file, "--workdir", workdir, "--global-dir", global_dir, "--run-dir", run_dir], start_new_session=True, env=get_env_with_gemini_key(...))` ensuring process group isolation and absolute paths. Rather than implicitly mutating the active queue, it explicitly transitions back to the execution state by formally loading the new PRs from the workspace and resetting the execution cursor, ensuring a deterministic FSM flow. If the retry limit is hit, transition to a blocked state and escalate.
- **Circuit Breaker & Strict JSON Contract:** Wrap the UAT verification call in `orchestrator.py` with a 3-strike retry loop. Do NOT use `utils_json.py` (Lossy Context Flattening) to scrape the UAT agent's output. The Verifier must output strict, compliant JSON that is parsed directly via `json.loads`. Raise a specific exception or set a `UAT_BLOCKED` state that breaks the main loop and triggers the Slack notification without cleaning the workspace if valid JSON is not received.
- **Planner Recovery Prompt:** In `spawn_planner.py`, if `--replan-uat-failures` is provided, load a dedicated system prompt. The prompt string MUST be exactly identical to the `planner_recovery_prompt` defined in Section 7 (Hardcoded Content).
- **Auditor Key Integration (DRY Principle):** Do NOT replicate the API key assignment logic in `spawn_auditor.py`. Extract the existing key assignment logic from `orchestrator.py` and other scripts into a shared module (e.g., `scripts/utils_api_key.py`). Refactor all relevant scripts, including `spawn_auditor.py`, to import and call this shared utility. MUST use `lock_utils.py` for concurrent-safe read/write access to `.session_keys.json` to prevent data races.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: UAT Detects Missing Requirements (Within Retries)**
  - **Given** The pipeline reaches the UAT phase, the system has retried fewer times than the configuration limit, and the UAT verifier outputs a report with missing items.
  - **When** the orchestrator processes this result.
  - **Then** it extracts the missing items, spawns a planner process forwarding all necessary context arguments (workdir, global-dir, etc.) to handle the failures, and resumes the execution pipeline by picking up the new PRs from the workspace.

- **Scenario 1B: UAT Missing Requirements (Exceeds Retries)**
  - **Given** UAT detects missing requirements but the system has already executed recovery attempts equal to the configured maximum limit.
  - **When** the orchestrator evaluates the state.
  - **Then** it performs a Hard Stop, writes `UAT_ERROR` to the workspace state file, and sends the hardcoded escalation alert.

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
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_arbitrator.py`
- `scripts/spawn_manager.py`
- `scripts/utils_api_key.py` (New file)
- `tests/test_utils_api_key.py` (New file)
- `tests/test_orchestrator_load_balancing.py`
- `tests/test_orchestrator.py`
- `tests/test_spawn_auditor.py`
- `tests/test_spawn_coder.py`
- `tests/test_spawn_reviewer.py`
- `tests/test_spawn_verifier.py`
- `tests/test_spawn_arbitrator.py`
- `tests/test_spawn_manager.py`
- `tests/test_spawn_planner.py`
- `tests/test_spawn_planner_uat.py` (New file)
- `config/sdlc_config.json.template`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Initial draft combining ISSUE-1152 and ISSUE-1162 logic.
- **Audit Rejection (v1.0)**: Rejected by Auditor due to String Determinism violation (missing Planner Recovery Prompt in Section 7) and DRY principle violation (Copy-Paste of API key assignment logic).
- **v2.0 Revision Rationale**: Moved prompt to Section 7. Mandated extraction of API key logic into `utils_api_key.py` to adhere to DRY principles.
- **Audit Rejection (v2.0)**: Rejected by Auditor due to Infinite Agentic Loop risk (no max retries for UAT recovery) and Implicit Queue Mutation (appending to queue instead of formal FSM transition).
- **v3.0 Revision Rationale**: Introduced `max_uat_recovery_attempts` config (default 5) and explicit FSM states (`STATE_UAT_RECOVERY`, `STATE_UAT_BLOCKED`) to ensure finite loops and deterministic execution.
- **v4.0 Revision Rationale**: Boss mandated rollback. Corrected the PRD design flaw where it assumed an incorrect UAT JSON schema. Ensured the BDD scenario and requirements explicitly instruct the orchestrator to parse the `verification_details` array from `uat_report.json` to extract missing items, matching the actual data contract of `spawn_verifier.py`.
- **Audit Rejection (v4.0)**: Rejected by Auditor due to Blast Radius leakage (missing `spawn_coder.py`, `spawn_reviewer.py`, etc., in Section 6) and String Determinism violation (missing hardcoded escalation alert for UAT retries exceeded).
- **Audit Rejection (v5.0)**: Rejected by Auditor due to String Determinism violation (JSON schema keys and `UAT_ERROR` not listed in Section 7), BDD violation (source-level FSM variables exposed), and critical Anti-patterns (relative path invocation breaking sandboxes; concurrent I/O on JSON without `lock_utils.py`).
- **v6.0 Revision Rationale**: Fixed BDD to test blackbox observable behavior only. Explicitly mandated `RUNTIME_DIR` for absolute path execution and mandated `lock_utils.py` for `.session_keys.json` data race prevention. Added JSON schema keys to Section 7.
- **Audit Rejection (v6.0)**: Rejected by Auditor due to Lossy Context Flattening (use of `utils_json.py` instead of strict JSON parser), implicit blast radius (missing `tests/test_orchestrator_load_balancing.py` in Section 6), and breaking architecture isolation (using `subprocess.run` instead of `dpopen`).
- **v7.0 Revision Rationale**: Replaced `subprocess.run` with `dpopen` to ensure process group isolation. Removed `utils_json.py` scraping to enforce strict JSON contracts. Appended `tests/test_orchestrator_load_balancing.py` to Section 6.
- **Audit Rejection (v7.0)**: Rejected by Auditor due to String Determinism violation (`max_uat_recovery_attempts` not in Section 7) and implicit blast radius (`config/sdlc_config.json.template` not in Section 6).
- **v8.0 Revision Rationale**: Added `max_uat_recovery_attempts` to Section 7 and `config/sdlc_config.json.template` to Section 6.
- **Audit Rejection (v8.0)**: Rejected by Auditor due to Blast Radius leakage (missing unit test files like `tests/test_orchestrator.py` in Section 6) and String Determinism (`STATE_UAT_RECOVERY` missing from Section 7).
- **v9.0 Revision Rationale**: Added `tests/test_orchestrator.py` and a new `tests/test_spawn_planner_uat.py` to Section 6. Added `STATE_UAT_RECOVERY` and `STATE_PLANNING_EVAL` to Section 7.
- **Audit Rejection (v9.0)**: Rejected due to implicit blast radius (missing test files for all `spawn_*.py` scripts and `utils_api_key.py`) and String Determinism (`UAT_BLOCKED` missing from Section 7).
- **v10.0 Revision Rationale**: Added all relevant test files to Section 6. Added `UAT_BLOCKED` and `UAT_ERROR` to Section 7 explicitly.

---

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:
- **`uat_escalation_alert` (For orchestrator.py - System Error)**: 
```text
🚨 *SDLC Pipeline Blocked: UAT Agent 发生系统级错误（如返回格式非法/超时）。现场已冻结，请人工介入排查。排查完毕后可使用 `--resume` 恢复执行。*
```

- **`uat_retry_exceeded_alert` (For orchestrator.py - Retries Exceeded)**:
```text
🚨 *SDLC Pipeline Blocked: UAT 补救次数已达上限。自动恢复流已熔断，现场已冻结，请人工介入处理。排查完毕后可使用 `--resume` 恢复执行。*
```

- **`uat_error_state` (For orchestrator.py - STATE.md payload)**:
```text
UAT_ERROR
```

- **`verification_json_keys` (For orchestrator.py - parsing uat_report.json)**:
```text
verification_details
status
MISSING
NEEDS_FIX
PASS
```

- **`config_keys` (For sdlc_config.json)**:
```text
max_uat_recovery_attempts
```

- **`uat_blocked_state` (For orchestrator.py - STATE.md payload)**:
```text
UAT_BLOCKED
```

- **`uat_error_state` (For orchestrator.py - STATE.md payload)**:
```text
UAT_ERROR
```

- **`fsm_states` (For orchestrator.py - Logging and state tracking)**:
```text
STATE_UAT_RECOVERY
STATE_PLANNING_EVAL
STATE_EXECUTING_PRS
STATE_UAT_BLOCKED
```

- **`planner_recovery_prompt` (For spawn_planner.py)**:
```text
作为一个架构师，不要重新规划已有的功能。请仔细阅读 UAT 报告中标记为 MISSING 的需求，生成专门针对这些遗漏点的新 Micro-PRs（例如 PR_UAT_Fix_1.md），确保不破坏现有代码。
```
