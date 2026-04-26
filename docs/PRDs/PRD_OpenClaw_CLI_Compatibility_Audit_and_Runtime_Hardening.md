---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: OpenClaw CLI Compatibility Audit and Runtime Hardening

## 1. Context & Problem (业务背景与核心痛点)
`ISSUE-1185` exposed that the current `leio-sdlc` runtime contains OpenClaw-specific CLI assumptions that are no longer valid against the currently installed OpenClaw version.

The failure first surfaced while executing the approved Planner-startup-envelope PRD through `engine=openclaw` and `model=gpt`. Multiple SDLC runs appeared to fail in `State 0: Auto-slicing PRD...`, creating the misleading impression that the Planner or the PRD itself was unstable. However, standalone runtime debugging narrowed the first-order failure to the installed OpenClaw integration path inside `scripts/agent_driver.py`.

Concrete findings from runtime diagnosis:
1. `openclaw_agent_exists()` assumed that `openclaw agents list` returns one raw agent id per line. The current CLI instead returns a human-readable multi-line card/list format (for example `- sdlc-generic-openclaw-gpt`, followed by workspace/model metadata), so existing agents can be misdetected as absent.
2. `validate_openclaw_agent_model()` invoked `openclaw agents show <agent_id>`, but the current CLI does not provide an `agents show` subcommand.
3. The existing unit/integration tests for the OpenClaw path had mocked the old contract so thoroughly that the incorrect assumptions were preserved and blessed instead of being caught. In particular, multiple tests hardcoded `agents list` as plain one-id-per-line output and asserted that `agents show` exists.

This means the problem is not limited to a single bug. It is a broader **CLI compatibility and test-strategy hardening gap**:
- runtime code made undocumented assumptions about OpenClaw CLI behavior,
- tests over-mocked the CLI boundary and failed to detect contract drift,
- `.dist` / deployed runtime artifacts inherited the same stale assumptions,
- future `openclaw ...` integration points may contain similar hidden mismatches.

The goal of this PRD is therefore intentionally twofold:
1. **Fix the known OpenClaw CLI compatibility bugs** in the runtime.
2. **Perform a bounded compatibility audit across existing OpenClaw CLI call sites** in `leio-sdlc`, recording which uses are valid, suspicious, or broken, and hardening the test strategy so future CLI drift is caught earlier.

This is a runtime integration hardening PRD, not a broad planner/reviewer/coder behavior redesign.

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. **Fix existing-agent detection on the OpenClaw path**
   - `scripts/agent_driver.py` must no longer assume `openclaw agents list` is one raw agent id per line.
   - It must correctly detect whether a target agent id exists against the current human-readable CLI output format.
   - The logic must be robust to additional metadata lines in the `agents list` output.

2. **Replace unsupported `agents show` dependency with current `agents list` model inspection**
   - The OpenClaw model-validation path must not rely on `openclaw agents show`.
   - For the currently supported CLI generation, model inspection must be derived from `openclaw agents list` output by parsing the per-agent card metadata (including the `Model:` line for the matching agent entry).
   - The runtime must continue to fail fast when the resolved isolated agent is bound to a different model than requested.

3. **Audit all runtime OpenClaw CLI call sites used by leio-sdlc execution paths**
   - Perform a bounded audit of executable `leio-sdlc` source-tree paths that invoke OpenClaw CLI commands.
   - The audit scope must explicitly include:
     - runtime Python execution paths (for example `scripts/agent_driver.py` and launchers that inherit it),
     - deploy / rollback shell scripts that invoke OpenClaw service commands,
     - test files whose purpose is to validate OpenClaw CLI contract behavior.
   - Historical PRDs, archived docs, and stale reference text may be recorded as informational findings, but they must not expand this PRD into a full documentation cleanup project.
   - Each discovered in-scope call site must be classified into one of three buckets:
     - confirmed valid against current CLI,
     - suspicious / needs stronger verification,
     - confirmed broken / incompatible.
   - The audit result must be recorded in a durable project artifact (for example a markdown report under `docs/` or `references/`) so the knowledge does not remain only in session history.

4. **Do not limit the fix to installed runtime hotpatching**
   - The source-tree implementation under `/root/projects/leio-sdlc` must be corrected.
   - The resulting source changes must be the canonical fix path for later deploy / release.
   - This PRD does not authorize leaving the fix only as an undocumented manual runtime patch under `~/.openclaw/skills/`.

5. **Bring `.dist` / release artifact expectations back into sync**
   - The fix must ensure that shipped runtime artifacts are not left with stale CLI assumptions after source correction.
   - If tests or build steps currently validate only source behavior but not shipped runtime behavior, this PRD must add the minimum necessary checks to reduce that gap.
   - This PRD does not require hand-editing `.dist` artifacts directly; it requires a source-driven path that results in packaged/runtime behavior matching the corrected source assumptions.

6. **Harden test strategy at the CLI boundary**
   - Any tests whose primary purpose is to validate OpenClaw CLI contract compatibility must not rely solely on fake `bin/openclaw` stubs.
   - For non-LLM-dependent CLI contract checks, add at least one real-CLI smoke layer using the actual installed OpenClaw CLI.
   - Mock-heavy tests may remain for state-machine or branch-coverage goals, but they must no longer be the only protection against CLI contract drift.

7. **Prioritize the OpenClaw path most responsible for the 1185 failure**
   - The highest-priority executable path to harden is the OpenClaw branch of `scripts/agent_driver.py` as used by Planner / Coder / Reviewer / Verifier / Auditor launchers.
   - Secondary call sites such as `openclaw message send` and `openclaw gateway restart` should be audited and classified, but only escalated into code changes if the audit finds real incompatibilities or missing verification coverage.
   - The PRD must not let those secondary paths dilute or delay the repair of the agent-management failure path that directly caused `ISSUE-1185`.

8. **Preserve current role semantics**
   - This PRD is not allowed to redesign Planner, Coder, Reviewer, Verifier, or Auditor prompt semantics.
   - The goal is runtime compatibility and CLI-boundary hardening, not role-behavior redesign.

### Non-Functional Requirements
1. The final runtime behavior must be compatible with the currently installed OpenClaw CLI surface, not a stale remembered interface.
2. The fix must minimize blast radius by targeting the runtime adapter layer and CLI-boundary tests first.
3. The audit output must be human-readable and durable so future SDLC work can rely on it.
4. The test strategy must meaningfully reduce the chance that future OpenClaw CLI changes silently break `leio-sdlc` runtime behavior.

### Explicit Non-Goals
- redesigning Planner / Coder / Reviewer / Verifier / Auditor prompts,
- replacing `openclaw agent` with an unrelated execution transport,
- doing a full all-command OpenClaw platform audit beyond the commands actually used by `leio-sdlc`,
- broad SDLC state-machine redesign unrelated to CLI compatibility,
- leaving the investigation only as a chat conclusion with no durable artifact.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Fix the adapter where the real bug lives
The first-order bug lives in the OpenClaw-specific adapter logic inside `scripts/agent_driver.py`.

Therefore the primary implementation strategy is:
- correct the source-tree OpenClaw adapter contract,
- verify it against the current real OpenClaw CLI,
- then harden tests so the same mismatch cannot survive again.

This PRD explicitly rejects the anti-pattern of treating the installed runtime hotpatch as the long-term fix. The installed runtime patch was useful for diagnosis, but the durable fix must land in source.

### 3.2 Known broken assumptions to remove
#### Broken assumption A: plain one-id-per-line `agents list`
Current source assumes:
- `openclaw agents list` emits raw ids suitable for exact line-set membership testing.

Current CLI reality:
- `agents list` emits human-readable card/list output, where the id appears in lines like:
  - `- sdlc-generic-openclaw-gpt`
- additional metadata lines follow.

Therefore:
- existence detection must parse the current output format rather than exact-match raw lines.
- the same parsed card output should become the current source of truth for model metadata lookup.

#### Broken assumption B: `agents show` exists
Current source assumes:
- `openclaw agents show <agent_id>` exists and can be parsed for model inspection.

Current CLI reality:
- `agents show` is not present.

Therefore:
- model validation must be implemented by extracting the matching agent card from `openclaw agents list` output and reading its `Model:` field.
- this PRD should not leave the replacement strategy abstract or provider-dependent.

### 3.3 Bounded OpenClaw CLI compatibility audit
The audit should focus on executable `leio-sdlc` paths that shell out to OpenClaw CLI commands.

Suggested audit buckets:
1. **Runtime-critical agent-management path**
   - `scripts/agent_driver.py`
   - any launchers whose OpenClaw path is inherited through `invoke_agent()`
2. **Message / notification path**
   - `openclaw message send` usage in runtime notification logic
3. **Gateway control path**
   - `openclaw gateway restart` or related service commands in deploy / rollback flows
4. **Test assumptions**
   - tests that stub OpenClaw output in a way that no longer matches reality

The audit output must explicitly label each in-scope executable or test contract path as:
- confirmed valid,
- suspicious / insufficiently verified,
- confirmed broken.

Historical docs and archived PRD text may be mentioned in a separate informational appendix if useful, but they must not become mandatory remediation scope for this PRD.

### 3.4 Test strategy redesign at the right boundary
The current weakness is not simply “too many mocks.”
The real weakness is that tests validating CLI compatibility mocked the CLI contract itself.

The corrected test strategy should be layered:
1. **Unit tests**
   - pure parsing helpers and local branch logic
2. **Mock-heavy integration tests**
   - orchestration/state-machine behavior where CLI realism is not the primary subject under test
3. **Real OpenClaw CLI smoke tests without real LLM dependence**
   - used when the purpose of the test is to validate:
     - command existence,
     - subcommand naming,
     - output parsing,
     - argument shape,
     - current CLI compatibility.

This means:
- tests for `agent_driver` OpenClaw adapter compatibility should gain a real-CLI smoke layer,
- deploy/rollback/message paths may keep mocks for behavior coverage but should gain at least minimal real-CLI existence/shape verification where appropriate,
- tests that require real LLM reasoning remain outside this category and may stay as canaries or dedicated live tests.

### 3.5 Deliver a durable compatibility report
The audit findings should be saved in a durable source-controlled artifact, for example:
- `docs/OpenClaw_CLI_Compatibility_Audit.md`
- or an equivalent well-scoped path in `references/`

That artifact should include at minimum:
- command surface inspected,
- call sites inspected,
- classification per call site,
- concrete broken assumptions discovered,
- which tests were upgraded or added to guard those assumptions.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Existing OpenClaw agents are correctly detected under current CLI output**
  - **Given** the current `openclaw agents list` human-readable output format
  - **When** the OpenClaw adapter checks whether `sdlc-generic-openclaw-gpt` exists
  - **Then** it correctly detects the existing agent
  - **And** it does not falsely fall into the lazy-create path

- **Scenario 2: Model validation does not depend on unsupported `agents show`**
  - **Given** the current OpenClaw CLI surface where `agents show` is unavailable
  - **When** the runtime validates the bound model for an existing isolated agent
  - **Then** it uses a supported current-CLI-compatible information source
  - **And** it still fails fast on a true model mismatch

- **Scenario 3: OpenClaw adapter works on the standalone planner path with current CLI semantics**
  - **Given** `spawn_planner.py` is executed directly with `engine=openclaw` and `model=gpt`
  - **When** the OpenClaw adapter path runs
  - **Then** it proceeds through agent existence detection and model validation without hitting stale CLI-contract failures
  - **And** the Planner can reach the actual `openclaw agent --agent ...` execution step

- **Scenario 4: Audit artifact records all relevant in-scope OpenClaw call sites and their status**
  - **Given** the source tree contains multiple OpenClaw CLI call sites
  - **When** the audit is completed
  - **Then** a durable report exists listing the inspected in-scope executable and test-contract call sites
  - **And** each is marked as confirmed valid, suspicious, or confirmed broken
  - **And** historical docs or archived references are clearly separated from mandatory remediation scope

- **Scenario 5: CLI-compatibility tests no longer rely only on fake OpenClaw binaries**
  - **Given** OpenClaw adapter tests whose primary purpose is CLI contract validation
  - **When** the updated test suite is inspected
  - **Then** at least one real OpenClaw CLI smoke layer exists for those adapter semantics
  - **And** stale mock-only assumptions such as one-id-per-line `agents list` output or `agents show` existence are no longer the sole guardrail
  - **And** those smoke tests do not require successful real LLM reasoning to pass

- **Scenario 6: Non-CLI runtime semantics are not unnecessarily redesigned**
  - **Given** this PRD implementation is applied
  - **When** Planner/Coder/Reviewer/Verifier/Auditor prompt semantics are reviewed
  - **Then** they are not broadly redesigned as part of this compatibility hardening work

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
The main risk is adapter drift: `leio-sdlc` shells out to a real external CLI, but tests have been validating a mocked, idealized contract instead of the current OpenClaw CLI reality. That allows real runtime breakage to hide behind green tests.

### Verification Strategy
1. **Source-level unit tests**
   - Add deterministic tests for parsing current `openclaw agents list` output.
   - Add deterministic tests for model extraction from the supported current output source.

2. **Adapter-level integration tests**
   - Update the OpenClaw adapter tests so they reflect the current real CLI output shape instead of stale simplified assumptions.
   - Remove or rewrite assertions that require `agents show`.

3. **Real OpenClaw CLI smoke tests, no real LLM reasoning required**
   - Add a smoke layer for command/subcommand existence and output-shape validation.
   - These smoke tests must not require successful provider inference or model-quality assertions; they are for CLI contract verification only.
   - Prioritize:
     - `openclaw agents list`
     - current `agents list`-derived model-validation path
     - minimal `openclaw agent` invocation contract where feasible without depending on successful model reasoning

4. **Audit artifact verification**
   - Add a check that the compatibility report exists and covers the intended runtime call sites.

### Quality Goal
Restore correctness of the OpenClaw runtime adapter and make CLI contract drift visible in CI before it can again masquerade as Planner/SDLC business-logic instability.

## 6. Framework Modifications (框架防篡改声明)
- `/root/projects/leio-sdlc/scripts/agent_driver.py`
- `/root/projects/leio-sdlc/tests/test_079_agent_driver_openclaw_lazy_create.py`
- `/root/projects/leio-sdlc/tests/test_083_openclaw_model_aware_routing.py`
- `/root/projects/leio-sdlc/tests/test_084_openclaw_model_mismatch_guardrail.py`
- `/root/projects/leio-sdlc/tests/` real OpenClaw CLI smoke test file(s) for adapter compatibility (new, if needed)
- `/root/projects/leio-sdlc/docs/` or `/root/projects/leio-sdlc/references/` compatibility audit artifact (new)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial issue was observed as repeated SDLC failures in `State 0: Auto-slicing PRD...` while trying to execute the Planner-startup-envelope PRD under `engine=openclaw`.
- **v1.1 diagnosis**: Standalone `spawn_planner.py` debugging showed the first-order failure was in the OpenClaw-specific `agent_driver.py` integration path rather than the Planner slicing logic itself.
- **v1.2 concrete root cause**: Two adapter-level CLI mismatches were identified:
  - existence detection assumed plain one-id-per-line `agents list` output,
  - model validation assumed a nonexistent `agents show` subcommand.
- **v1.3 testing lesson**: Adapter tests had mocked the stale contract too faithfully, so they did not protect the real CLI boundary.
- **v1.4 scope decision**: The fix must include both the known runtime bug repair and a bounded audit/hardening of other OpenClaw CLI call sites used by `leio-sdlc`.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`openclaw_agent_exists_known_bad_assumption`**:
```text
return agent_id in {line.strip() for line in (list_stdout or '').splitlines() if line.strip()}
```

- **`unsupported_openclaw_agents_show_invocation`**:
```text
show_cmd = [cmd_exec, 'agents', 'show', agent_id]
```

- **`required_replacement_model_validation_source`**:
```text
openclaw agents list
```

- **`compatibility_audit_classifications`**:
```text
confirmed valid
suspicious / needs stronger verification
confirmed broken
```

- **`openclaw_cli_priority_smoke_targets`**:
```text
openclaw agents list
current model-validation info path
openclaw agent
```

- **`openclaw_agent_management_targets`**:
```text
sdlc-generic-openclaw
sdlc-generic-openclaw-gpt
```
