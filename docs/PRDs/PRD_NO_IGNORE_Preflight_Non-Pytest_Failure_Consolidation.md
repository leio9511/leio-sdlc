---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Preflight Non-Pytest Failure Consolidation

## 1. Context & Problem (业务背景与核心痛点)
在 explicit empty-ignore full-audit mode 的本地 contract 语义下，`leio-sdlc` 需要确保相关 preflight/test-harness 行为与该模式一致，而不是把历史 debt-quarantine 状态硬编码成唯一合法输入。

经过前几轮清理后，当前需要收口的 **non-pytest** 问题主要集中为两类：

1. **`scripts/e2e/mocked/e2e_test_preflight_guardrails.sh` 的 full-audit / empty-ignore compatibility 问题**
   - 该测试假设 `ignore_tests.json` 必须非空；
   - 但 explicit empty-ignore full-audit 场景下，空 ignore manifest 是合法输入；
   - 因此它会在本地 contract 验证中以 `AssertionError: {'bash': [], 'pytest': []}` 失败。

2. **`scripts/test_planner_slice_failed_pr.sh` 的 sandbox/bootstrap contract 问题**
   - 该脚本在 `setup_sandbox()` 内使用 `GLOBAL_MOCK_DIR` 之前并未先初始化该变量；
   - 历史上它已在 Epic #8 中被记录为 `GLOBAL_MOCK_DIR` 初始化顺序错误，可能扩展到 `/.sdlc_runs/...` 并触发权限或路径错误；
   - 这是一个 bash test harness / mock-global-dir setup 问题，而不是产品主逻辑问题。

这两类失败都具有共同特征：
- 它们不是产品行为回归，而是 **preflight/test-harness contract** 问题；
- 它们需要在本地、聚焦、可自动闭环的验证范围内被修复；
- 它们更适合作为同一轮 **non-pytest failure consolidation** 一起处理，但必须保持问题边界清晰。

本 PRD 的目标不是修复所有剩余 failures，也不是触碰 pytest umbrella 问题，而是：

> **一次性收口 explicit empty-ignore full-audit mode 下最明确、最独立的两项本地 non-pytest contract/harness 问题：preflight guardrails 的 empty-ignore compatibility，以及 planner slice failed PR bash test 的 mock/sandbox setup contract 问题。**

本 PRD 不覆盖：
- `Pytest functional & unittest suite` 里剩余的 path portability / command-assertion drift 问题；
- 对 `ignore_tests.json` fail-closed 语义的放松；
- 通过重新填回 ignore list 来制造假绿；
- 与 test harness contract 无关的 planner / orchestrator 产品逻辑重构；
- `NO_IGNORE` branch promotion、GitHub-hosted preflight run、manual witness capture、或任何外部验证取证流程。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须修复 `e2e_test_preflight_guardrails.sh` 对空 ignore manifest 的错误假设**
   - 必须明确：空的 `ignore_tests.json`（`{"bash": [], "pytest": []}`）在 deliberate full-audit / explicit empty-ignore 场景下是否属于合法输入；
   - 若属于合法输入，则 `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh` 必须兼容该模式；
   - 若不属于合法输入，则必须改为清晰 codify alternative full-audit procedure，并同步调整测试与文档；
   - 无论采用哪种路径，都必须保留 malformed / missing ignore manifest 的 fail-closed 语义。

2. **必须修复 `scripts/test_planner_slice_failed_pr.sh` 的 sandbox / mock-global-dir 初始化问题**
   - `setup_sandbox()` 中不得继续在 `GLOBAL_MOCK_DIR` 初始化之前使用该变量；
   - 脚本在创建 mock `.sdlc_runs` 路径时必须使用已定义、可控、对 clean runner 安全的 target path；
   - 修复后，测试必须仍然验证：
     - planner 正常创建 mock PRs；
     - missing `--slice-failed-pr` target 仍然触发 `[Pre-flight Failed]`；
     - successful slice 仍然验证 `--insert-after` 与 failed PR contract path 注入；
     - sub-id slice (`PR_002_1_...`) 仍然验证正确 insert-after 位置。

3. **两类修复必须保持问题边界清晰，不得互相污染**
   - `#28` 对应的是 full-audit ignore-manifest contract；
   - `test_planner_slice_failed_pr.sh` 对应的是 bash sandbox/mock-dir setup contract；
   - 同一轮可以执行，但实现中不得把它们混成一个模糊的“随便改到绿”为止的问题。

4. **不得通过重建 quarantine 状态来达成 green**
   - 在本地 contract 验证中，不允许通过把 ignore manifest 填回非空来掩盖 `#28`；
   - 不允许通过将 `scripts/test_planner_slice_failed_pr.sh` 重新加入 ignore 来回避修复；
   - 成功必须建立在真实本地 contract/harness 行为上，而不是恢复历史 quarantine 状态。

5. **修复后必须继续保持测试的原始业务意义**
   - `e2e_test_preflight_guardrails.sh` 仍然必须验证 preflight contract 的 fail-closed / quarantine / full-surface behavior，而不是被弱化成空壳；
   - `scripts/test_planner_slice_failed_pr.sh` 仍然必须验证 planner slicing contract，而不是只让脚本不崩溃。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 优先修改测试文件本身与其最小 supporting helper / fixture path；
   - 不应顺带重构 planner / orchestrator / preflight 主逻辑，除非某个最小 supporting contract 变更不可避免且能被清晰解释。

2. **本地聚焦验证必须是设计目标**
   - 本 PRD 的成功不是“默认 master + ignore list 下通过”；
   - 而是 explicit empty-ignore contract 下这两类 non-pytest failure 在本地、聚焦、可自动闭环的验证面上被真实修复。

3. **必须保留 fail-closed 安全语义**
   - malformed / missing ignore manifest 仍然应让 preflight fail closed；
   - 不允许为兼容 full-audit 而削弱原有安全边界。

### User Stories

- **As a maintainer**, I want the remaining non-pytest contract/harness failures reduced without restoring hidden quarantine assumptions, so the local preflight semantics stay truthful and executable.
- **As a reviewer**, I want the preflight-guardrails test to distinguish legitimate audit mode from malformed manifest inputs, so the test reflects contract intent rather than the repository’s temporary debt state.
- **As an operator**, I want the planner slice bash test to use a correctly initialized mock-global-dir contract, so real regressions in slice behavior are not obscured by harness setup bugs.
- **As a future test author**, I want full-audit compatibility and mock sandbox setup rules to be explicit, so these failures do not recur when quarantine state changes.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **dual-slice non-pytest test-contract consolidation** 路线：
- Slice A: preflight guardrails full-audit compatibility
- Slice B: planner slice failed PR sandbox/mock-dir setup correctness

### 3.1 核心设计决策

1. **将 explicit empty-ignore full-audit mode 视为合法的 full-surface observability mode，而不是异常 hack**
   - 如果仓库仍需要 full-audit / empty-ignore practice 来形成真实 backlog surface，则相关测试必须兼容这一模式；
   - 不能把“当前 debt quarantine 习惯”硬编码成唯一合法 contract。

2. **保留 fail-closed 与支持 empty-manifest 是两个不同层次的 contract**
   - malformed / missing manifest 仍应 fail closed；
   - explicit empty manifest 可被视为合法 full-audit input；
   - 测试必须反映这种区别，而不是把两者混为一谈。

3. **`scripts/test_planner_slice_failed_pr.sh` 修复的是 harness bootstrap，不是 planner 产品逻辑**
   - 重点是让 mock global run directory setup 先定义、再使用；
   - 不是为了 green 而改写 planner slicing semantics。

4. **一个 PRD 可以覆盖两类 non-pytest failures，但必须拆成独立执行切片**
   - 两者可以同一波做，减少往返；
   - 但 Planner / Coder / Reviewer 必须把它们视为两个不同根因、不同验收点的切片，而不是一个模糊大修。

### 3.2 推荐实现方向

#### A. `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- 明确 full-audit / empty-ignore manifest 是否是合法模式；
- 若合法：
  - 保留“non-empty manifest yields debt-quarantine green”的断言；
  - 新增/保留“empty manifest restores full discovery surface and fails on real failing sentinel”断言；
  - 不再把空 manifest 当成错误；
- 若不合法：
  - 必须改成另一个显式 full-audit procedure，并让测试和文档都对齐。

#### B. `scripts/test_planner_slice_failed_pr.sh`
- 先初始化 `GLOBAL_MOCK_DIR`，再在 `setup_sandbox()` 或等价路径中消费它；
- 或将 `setup_sandbox()` 重构为显式接收 mock-global-dir 参数，但必须保持脚本易读、低 blast radius；
- 任何修复都必须保留 Scenario 1–4 的 slicing 断言行为。

### 3.3 明确不采用的方案

1. **不通过把 ignore list 填回去修 #28**
   - 这会制造 full-surface 假绿，而不是修复测试 contract。

2. **不通过 skip / weaken assertions 修 planner slice test**
   - 这会把 harness bug 伪装成产品行为通过。

3. **不把两类问题混成一次大范围 preflight 重构**
   - 本 PRD 只收口这两个 non-pytest failure，不处理整个 pytest umbrella 或其他历史 debt。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Preflight guardrails distinguishes non-empty quarantine mode from empty-manifest full-audit mode**
  - **Given** a sandboxed preflight fixture with a valid non-empty `ignore_tests.json`
  - **When** `preflight.sh` is executed
  - **Then** the run produces quarantine-green behavior for the listed targets
  - **And** the ignored sentinel targets do not execute

- **Scenario 2: Empty ignore manifest restores full discovery surface instead of being treated as an invalid input**
  - **Given** a sandboxed preflight fixture with a valid explicit empty `ignore_tests.json`
  - **When** `preflight.sh` is executed against failing sentinel tests
  - **Then** the full discovery surface is restored
  - **And** the run fails because the failing sentinel is no longer quarantined

- **Scenario 3: Malformed or missing ignore manifest still fails closed**
  - **Given** a sandboxed preflight fixture with a missing or malformed `ignore_tests.json`
  - **When** `preflight.sh` is executed
  - **Then** the run fails closed
  - **And** the fail-closed statement remains observable

- **Scenario 4: Planner slice failed PR test passes all intended slicing scenarios in a clean environment**
  - **Given** a clean test environment for `scripts/test_planner_slice_failed_pr.sh`
  - **When** the script is executed
  - **Then** the script exits successfully
  - **And** all intended planner slicing scenarios pass

- **Scenario 5: Scope boundary remains local and deterministic**
  - **Given** this PRD is executed through the automated SDLC pipeline
  - **When** implementation and review are performed
  - **Then** acceptance is decided only by repository-local contract/harness evidence
  - **And** no target-branch promotion, GitHub-hosted workflow run, final failure-summary witness, or manual external proof is required for completion of this PRD

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
当前最大的风险不是“又多两个红点”，而是：

1. full-audit / empty-ignore contract 被仓库自己的 guardrail test 误判为非法场景，导致本地 contract 语义被内部测试反向阻塞；
2. planner slice 测试继续因为 harness/bootstrap bug 失败，掩盖真实 planner slicing 回归；
3. 为了追求表面 green，把 ignore manifest 填回去或重新 quarantine 测试，制造假绿；
4. 修复过程中顺手改坏 fail-closed 语义或 planner 产品断言；
5. 执行层把本地 contract/harness 修复错误扩张为 target branch、GitHub workflow、或 manual witness 取证任务，导致边界失控。

### Verification Strategy

#### A. Contract-mode verification
需要验证：
- non-empty ignore manifest 与 empty-manifest full-audit mode 都有清晰可观察的行为；
- malformed / missing manifest 仍 fail closed；
- 这些模式边界由测试显式表达，而不是靠临时状态隐含表达。

#### B. Harness correctness verification
需要验证：
- `scripts/test_planner_slice_failed_pr.sh` 的 mock global run directory 初始化顺序正确；
- 脚本不再因为 harness setup bug 失败；
- 但 planner slicing assertions 仍然存在并有效。

#### C. Scope-boundary verification
需要覆盖：
- 本 PRD 的完成标准仅依赖 repository-local evidence；
- 不要求 target branch promotion；
- 不要求 GitHub-hosted workflow run；
- 不要求 manual witness artifact 或外部 failure-summary 取证。

### Quality Goal
本 PRD 的质量目标不是“让默认带 ignore 的 master CI 更绿”，而是：

> **让 explicit empty-ignore contract 下剩余的 non-pytest harness/contract failures继续收缩，确保相关本地 preflight 语义是合法、可观察、可验证的，同时让 planner slice bash test 反映真实 slice behavior 而不是 setup bug。**

补充边界：本 PRD 的完成不要求任何 target branch promotion、GitHub-hosted `Preflight`、manual witness、或外部取证流程；它只要求当前这两类 non-pytest failures 在 repository-local verification 范围内被真实推进过去。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/test_planner_slice_failed_pr.sh`
- `preflight.sh`（仅在需要最小 supporting clarification 且不改变 fail-closed truthful semantics 的前提下）
- `ignore_tests.json`（仅允许验证 empty-ignore contract，不授权通过恢复非空清单制造假绿）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 在逐步清理 bash / mocked E2E / Python git bootstrap debt 后，本地 contract 验证暴露出剩余 non-pytest failures：preflight guardrails 的 empty-ignore compatibility，以及 planner slice failed PR 的 harness bootstrap 问题。
- **Observed correction**: 这两项问题虽然可能出现在同一轮验证中，但根因不同：一个是 audit-mode contract，另一个是 sandbox/mock-dir setup contract。
- **v2.0 Revision Rationale**: 将两者合并为同一轮 non-pytest failure consolidation，以减少往返，但要求在执行层明确拆为独立切片，避免问题边界混淆。
- **v3.0 Scope Tightening**: 将 `NO_IGNORE` branch promotion、GitHub-hosted workflow、以及 manual witness 从自动执行范围中移除，确保本 PRD 只覆盖 repository-local contract/harness remediation。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **For `preflight.sh` / preflight guardrails contract**:
```text
If ignore_tests.json is missing or malformed, preflight must fail closed.
A non-empty ignore list may produce debt-quarantine green, which is distinct from true full green.
```

- **For `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh` observable contract markers**:
```text
[Pre-flight Failed]
debt-quarantine green
```

- **For `scripts/test_planner_slice_failed_pr.sh` planner slicing contract markers**:
```text
[Pre-flight Failed]
--insert-after 001
--insert-after 002_1
failed_pr_contract
"required": true
"priority": 1
```

