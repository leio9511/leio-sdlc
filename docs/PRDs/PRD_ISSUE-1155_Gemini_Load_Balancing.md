---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: ISSUE-1155_Gemini_Load_Balancing

## 1. Context & Problem (业务背景与核心痛点)
When running the SDLC orchestrator with the Gemini engine, we rely heavily on Long Context Caching to save tokens and maintain continuity. However, high-frequency queries easily trigger Google's `429 Too Many Requests` API limits. We need to introduce a pool of API Keys to load-balance the traffic. 

The core architectural constraint is: **Gemini Context Caches are tied to the exact Session ID and the original API Key that created them.** If an agent switches its API Key mid-session, it will suffer a catastrophic Cache Miss (or 404 error). Therefore, we need an intelligent load-balancing mechanism that achieves **Least-Connection distribution** across concurrent processes, while strictly guaranteeing **Session-Level Stickiness** across retries and `--resume` workflows.

## 2. Requirements & User Stories (需求定义)
1. **Zero-Configuration Backward Compatibility**: If no API keys are explicitly configured, the system must degrade gracefully and continue to use the environment's default key without throwing errors or running any load-balancing logic.
2. **Session-Level Stickiness**: Once an LLM Session ID is assigned an API Key index, it must permanently stick to that index. Planners and Coders have different session IDs, so they can run on different keys, but a Coder resuming work must use its original key.
3. **Stateful Session Mapping (Anti-Drift Stickiness)**: API keys should be assigned dynamically on the first encounter of a session and immediately persisted to a state file. This guarantees absolute stickiness for `--resume` or retries, even if the underlying `gemini_api_keys` pool size is modified by Ops mid-flight, averting catastrophic global cache misses.
4. **Resilient 429 Backoff**: Upon encountering a 429 limit, the process must hold its ground (exponential sleep backoff) using the exact same API key. It MUST NOT switch keys.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
**Target Modules**: `scripts/orchestrator.py` (Delegator) and `scripts/agent_driver.py` (Executor)

**Step 1: Configuration Opt-In (`orchestrator.py`)**
- Read `config/sdlc_config.json`. Check for the key `"gemini_api_keys"`. 
- If missing/empty, it passes no specific key, and the system degrades gracefully without load-balancing.

**Step 2: High-Level Stateful Assignment (`orchestrator.py`)**
- Move all stateful I/O out of the hot-path `agent_driver.py` to prevent Synchronous I/O Bottlenecks.
- The mapping file `.sdlc_runs/.session_keys.json` serves as the Single Source of Truth (SSOT).
- **Read/Write Access**: `orchestrator.py` must wrap all reads and writes to this file using `scripts/lock_utils.py` (or `fcntl.flock`) to ensure atomic operations and prevent Shared Mutable State corruption under concurrency.
- **Stable Identity Lookup (Anti-Positional Coupling)**: Load the JSON file. If `session_key` exists, retrieve its `key_fingerprint` (e.g., the last 8 chars of the originally assigned API key).
  - Search the current `gemini_api_keys` pool for a string that ends with this fingerprint. If a match is found, return the full key string.
  - **CRITICAL DEGRADATION**: If the fingerprint is NOT found in the current pool (e.g., Ops permanently deleted that specific key mid-flight), the system MUST gracefully degrade by discarding the stale mapping and proceeding to First Assignment to prevent a crash or Cache Miss.
- **First Assignment**: If `session_key` is missing (or gracefully degraded):
  1. Compute a deterministic pseudo-random index based on the current pool size: `idx = int(hashlib.md5(session_key.encode("utf-8")).hexdigest(), 16) % len(gemini_api_keys)`.
  2. Select the full key string at `gemini_api_keys[idx]`.
  3. Extract its fingerprint (e.g., `key[-8:]`) and persist `{"<session_key>": "<key_fingerprint>"}` into the JSON file and save. DO NOT persist the array index.
  4. Return the selected full key string.

**Step 3: Execution (Stateless Environment Injection)**
- `orchestrator.py` injects the selected key into the CLI subprocess call (`spawn_*.py` -> `agent_driver.py`) using `--env GEMINI_API_KEY=...` equivalence, or by safely overriding it via localized environment inheritance.
- `agent_driver.py` natively inherits this `GEMINI_API_KEY` from its environment scope, executing strictly as a stateless conduit. It performs absolutely zero file I/O or locking for key management.
- The existing exponential backoff loop in `agent_driver.py` naturally handles 429 limits using the inherited key.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Backward Compatibility (No Keys Configured)**
  - **Given** The `config/sdlc_config.json` lacks the `gemini_api_keys` field
  - **When** A test harness script invokes the agent logic
  - **Then** The script output must confirm the agent executed normally without interacting with `.sdlc_runs/.session_keys.json` and without emitting any custom load-balancing logs.

- **Scenario 2: First Execution (Stateful Persistence via Orchestrator)**
  - **Given** Multiple API keys are configured, and `.sdlc_runs/.session_keys.json` is empty.
  - **When** A test harness script invokes the orchestrator assignment logic with a new `session_key`
  - **Then** The script output must confirm an assignment was made, and the `key_index` must be physically persisted in `.sdlc_runs/.session_keys.json`.

- **Scenario 3: Anti-Drift Stickiness (Ops Pool Modification)**
  - **Given** `.sdlc_runs/.session_keys.json` contains a mapping of `session_xyz` to fingerprint `xyz123`, and the `gemini_api_keys` configuration is drastically re-ordered or resized (e.g., key is moved from index 0 to index 5).
  - **When** A test harness script invokes the orchestrator assignment logic for `session_xyz`
  - **Then** The script output must confirm that the logic strictly bypasses reassignment, correctly matches the fingerprint `xyz123` to the same actual API key regardless of its new array index, and returns the correct string, averting global index drift.

- **Scenario 4: Graceful Degradation (Ops Key Deletion)**
  - **Given** `.sdlc_runs/.session_keys.json` contains a mapping of `session_xyz` to fingerprint `xyz123`, but the specific API key matching `xyz123` has been permanently deleted from the `gemini_api_keys` configuration.
  - **When** A test harness script invokes the orchestrator assignment logic for `session_xyz`
  - **Then** The logic must intercept the missing key hazard, gracefully degrade by recalculating a new valid mapping from the remaining pool, overwrite the stale fingerprint in the state file, and return a valid key string without crashing.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Quality Goal**: Ensure stateless and lock-free load balancing within the hot-path execution (`agent_driver.py`), delegating state management exclusively to the `orchestrator.py` lifecycle.
- **Testing Approach (Observable Test Harness)**: 
  - The Coder MUST write an integration test script (`scripts/e2e/mocked/e2e_test_orchestrator_load_balancing.sh`).
  - This script will inject a mock `sdlc_config.json`, run concurrent Python harness invocations against the orchestrator's assignment function to verify file-lock stability, and dynamically alter the mock config size to test Anti-Drift Stickiness.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/agent_driver.py`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: Initial baseline capturing the PM and Boss discussion regarding Lifecycle Sticky mapping and Liveness-Probing Load Balancing.
- **Audit Rejection (v2.0)**: Rejected due to BDD non-testability (agent_driver lacks CLI) and Configuration Contamination (modifying files in static config/ dir).
- **v9.0 Revision Rationale**: 
  1. Addressed the 'IndexError Hazard' architecture rejection from the Auditor.
  2. Implemented Graceful Degradation logic in `orchestrator.py` to intercept and recalculate out-of-bounds `key_index` values caused by dynamic Ops configuration shrinkage.
  3. Re-enforced Section 7 with the explicit `.sdlc_runs/.session_keys.json` file path.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**

### Exact Text Replacements:
- **Configuration Key Name**:
```text
gemini_api_keys
```
- **Environment Variable Name**:
```text
GEMINI_API_KEY
```
- **Session Stickiness JSON File Path**:
```text
.sdlc_runs/.session_keys.json
```