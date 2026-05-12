---
Affected_Projects: leio-sdlc
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Fix Agent Driver Subprocess Pipe Hang via File Redirection

## 1. Context & Problem (业务背景与核心痛点)

### Current Behavior
`scripts/agent_driver.py` invokes spawned agents (gemini CLI / openclaw CLI) with:

```python
result = subprocess.run(cmd, capture_output=True, text=True, env=run_env)
```

`capture_output=True` internally creates `stdout=PIPE, stderr=PIPE`. These pipe file descriptors are inherited via `fork()` by any background/descendant processes spawned inside the agent session.

### The Hang Mechanism
1. The direct child process (e.g., gemini CLI) exits normally.
2. Background descendant processes still hold the write end of the inherited pipe FDs.
3. `subprocess.run` internally calls `communicate()`, which waits for pipe EOF.
4. EOF never arrives because the write end is still held open by descendant processes.
5. The SDLC pipeline hangs indefinitely — no error, no timeout, just a frozen orchestrator.

### Why subprocess.run with timeout doesn't fix this
`subprocess.run(cmd, timeout=N)` calls `process.kill()` on timeout, but this only kills the direct child. Background descendants outside the child's process group are unaffected. Their inherited pipe FDs remain open, and the parent still hangs waiting for EOF.

### Impact
- SDLC pipeline can appear stuck indefinitely
- No error signal to orchestrator — silent failure
- Affects all agent roles (planner, coder, reviewer, verifier, auditor) since all use the same `invoke_agent()` path
- Particularly likely in longer-running sessions where agents spawn background work

## 2. Requirements & User Stories (需求定义)

### Functional Requirements

**FR-1: Eliminate Inherited Pipe FD Problem**
Replace `subprocess.run(..., capture_output=True)` with `subprocess.Popen(..., stdout=file, stderr=file)` so agent stdout/stderr are redirected to temporary files instead of pipes. File FDs inherited by background descendants do not prevent the parent from waiting for the main process to exit.

**FR-2: No Timeout Introduced**
The fix MUST NOT impose an execution timeout on agent sessions. Agents must be free to execute for however long their task requires. The only change is HOW output is captured, not how long execution may take.

**FR-3: Cleanup Temporary Files**
Temporary stdout/stderr files MUST be deleted after their contents are read, even if the agent process exits with a non-zero code or is interrupted. Use `try/finally` or equivalent to guarantee cleanup.

**FR-4: Preserve Existing API Surface**
`invoke_agent()` MUST continue to return `AgentResult(session_key, stdout, stderr, return_code)`. The caller interface is unchanged — only the internal capture mechanism changes.

**FR-5: Process Group Isolation**
Use `start_new_session=True` in `subprocess.Popen` to isolate the spawned agent and its descendants into an independent process session. This has no runtime effect during normal execution but provides a clean signal boundary for any future process-management needs.

**FR-6: Retry Loop Compatibility**
The existing 3-attempt retry loop in `invoke_agent()` MUST continue to function correctly. Each retry must use fresh temporary files.

### Non-Functional Requirements
- **NFR-1**: No new external dependencies.
- **NFR-2**: Test mode (`SDLC_MOCK_LLM_RESPONSE`) must continue to work without change.
- **NFR-3**: GEMINI_API_KEY environment variable inheritance must be preserved.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### Target File
- **`scripts/agent_driver.py`** — Modify the `invoke_agent()` function only. No other files affected.

### Design Decision: Files over Timeouts
The core insight is that the problem is **pipe FD inheritance**, not execution duration. Therefore:
- **Rejected**: Adding a global timeout (would kill legitimate long-running agents).
- **Rejected**: Complex process-group monitoring from the orchestrator (too many moving parts, cross-component coupling).
- **Chosen**: File redirection — neutral to execution duration, surgically fixes the FD inheritance problem, and preserves the existing API surface.

### Change Points

**Before (current):**
```python
result = subprocess.run(cmd, capture_output=True, text=True, env=run_env)
# ... use result.stdout, result.stderr
```

**After (target):**
```python
# Create temp files for stdout/stderr
stdout_fd, stdout_path = tempfile.mkstemp(prefix="sdlc_stdout_", dir=temp_dir)
stderr_fd, stderr_path = tempfile.mkstemp(prefix="sdlc_stderr_", dir=temp_dir)

try:
    with os.fdopen(stdout_fd, 'w') as stdout_file, \
         os.fdopen(stderr_fd, 'w') as stderr_file:
        process = subprocess.Popen(
            cmd,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
            env=run_env,
        )
        return_code = process.wait()

    # Read captured output from files
    with open(stdout_path, 'r') as f:
        stdout = f.read()
    with open(stderr_path, 'r') as f:
        stderr = f.read()
finally:
    os.remove(stdout_path)
    os.remove(stderr_path)
```

### Why this works
- `stdout=stdout_file` → agent writes to a regular file. The write end is a file descriptor to disk, not a pipe.
- Background descendants inherit the file FD, not a pipe FD. Even if they keep it open, the parent doesn't care — it's waiting for `process.wait()` on the main process, not for pipe EOF.
- `process.wait()` returns as soon as the main agent process exits, regardless of descendant state.
- `start_new_session=True` provides process-group containment as a bonus.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Normal execution output preserved**
  - **Given** an agent session that produces stdout and stderr output
  - **When** `invoke_agent()` returns
  - **Then** `AgentResult.stdout` contains the full captured stdout and `AgentResult.stderr` contains the full captured stderr, identical to the pre-change behavior

- **Scenario 2: Background descendant does not cause hang**
  - **Given** an agent session that spawns a background child process which inherits stdout/stderr and keeps running after the main agent exits
  - **When** the main agent process exits
  - **Then** `invoke_agent()` returns within 5 seconds of the main process exit, regardless of background descendant state

- **Scenario 3: Temporary files cleaned up on success**
  - **Given** a successful agent invocation
  - **When** `invoke_agent()` returns
  - **Then** no temporary stdout/stderr files remain on disk

- **Scenario 4: Temporary files cleaned up on failure**
  - **Given** an agent invocation that exits with non-zero return code
  - **When** `invoke_agent()` returns or raises
  - **Then** no temporary stdout/stderr files remain on disk

- **Scenario 5: Retry loop functions correctly**
  - **Given** the first agent attempt returns non-zero exit code
  - **When** the retry loop executes attempt 2
  - **Then** fresh temporary files are created for the retry, independent of the first attempt's files

- **Scenario 6: Mock test mode unaffected**
  - **Given** `SDLC_MOCK_LLM_RESPONSE` environment variable is set
  - **When** `invoke_agent()` is called
  - **Then** the mock response path is taken before the new Popen logic, returning `AgentResult` with mock data as before

- **Scenario 7: API key inheritance preserved**
  - **Given** `GEMINI_API_KEY` is set in the parent environment
  - **When** the agent subprocess is spawned
  - **Then** the subprocess environment contains `GEMINI_API_KEY` with the correct value

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core Quality Risk
The primary risk is **regression in output capture** — the new file-based mechanism must capture stdout/stderr identically to the pipe-based mechanism.

### Test Strategy
1. **Unit Test**: Write a test in `tests/test_agent_driver.py` (or add to existing) that:
   - Spawns a real subprocess that writes known strings to stdout and stderr
   - Spawns a background descendant process that keeps a file FD open after the main process exits
   - Asserts `invoke_agent()` returns with correct stdout/stderr within a bounded time (< 10 seconds)
   - Asserts temp files are cleaned up

2. **Integration**: Run `./preflight.sh` to ensure existing test suites pass with no regressions.

3. **Smoke Test**: Run a single-PR SDLC cycle to confirm end-to-end agent spawning still works correctly.

### No Mocking Required for Core Behavior
The test spawns real subprocesses, which is the correct verification strategy for a subprocess-management fix.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py` — modify `invoke_agent()` subprocess invocation

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial draft — replace `subprocess.run(capture_output=True)` with `subprocess.Popen` + file redirection + `start_new_session=True` to eliminate pipe FD inheritance hang.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

None. This PRD involves only a change to the subprocess invocation mechanism. No new error messages, log strings, or configuration keys are introduced. The existing `AgentResult` dataclass and `invoke_agent()` function signature are preserved as-is.
