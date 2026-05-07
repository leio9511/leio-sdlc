---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Fix Clean Runner Git Identity Dependencies in Orchestrator Bash Tests

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 的 GitHub CI `Preflight` 现在已经接通，并且通过 `report-all` 模式开始暴露更完整的 clean-runner failure surface。当前一组最早需要处理的失败项集中在 orchestrator 启动/契约相关的 bash 测试上：

- `scripts/test_missing_channel.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`

从当前行为看，这些测试的失败高度怀疑并不是 orchestrator 主逻辑本身先坏了，而是测试在临时 sandbox git repo 里执行 `git commit` 时，隐式依赖了宿主机已经存在的 global git identity（如 `user.name` / `user.email`）。

这会造成一个危险假象：
- 在作者本地机器上，因为已有 global git config，这些测试可能通过；
- 在 GitHub-hosted clean runner 上，因为没有预置的 global identity，这些测试可能在真正进入 orchestrator 验证路径之前就失败；
- 于是 CI 报红时，看起来像 orchestrator / startup contract 问题，但本质上先是 test harness 不自洽。

因此，本 PRD 的目标不是直接修改 orchestrator 业务逻辑，而是先把这组 bash sandbox tests 的**最小 git 仓库构造契约**修正确保：

> **测试必须在没有任何预置 global git identity 的 clean sandbox 中，仍然能自给自足地完成最小初始化，并真正跑到它们各自要验证的 orchestrator 行为路径。**

本 PRD 不覆盖：
- `pytest tests/` 大盘子的 clean-runner failure recovery；
- mocked E2E broader regressions；
- `scripts/test_pr_003.sh` 的特定业务/历史回归；
- full-audit / ignore-manifest compatibility 问题；
- 对 orchestrator 主逻辑做与本问题无关的重构。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **这组 bash sandbox tests 必须不依赖宿主机已有的 global git identity**
   - 测试必须自行在临时 repo 中配置完成最小 `git commit` 所需的 repo-local identity，或采用等价方式确保不会依赖外部全局配置。

2. **测试必须在真正进入目标 orchestrator 验证路径后再判定成功/失败**
   - `test_missing_channel.sh` 的目标是验证 missing channel startup path；
   - `test_missing_force_replan.sh` 的目标是验证 missing force-replan startup contract；
   - `test_orchestrator_logs.sh` 的目标是验证 orchestrator file logging / scan trace behavior。
   - 不允许测试在前置 repo 初始化阶段就因为 git identity 缺失而提前失败。

3. **clean-runner parity 必须被显式纳入测试设计**
   - 测试设计应尽量模拟“没有宿主机 global git config 可用”的场景；
   - 不得默认假设开发者本地环境与 GitHub runner 等价。

4. **修复范围应最小化**
   - 优先修测试 harness；
   - 只有当 harness 修正后仍然失败，且能证明是 orchestrator 主逻辑问题时，才进一步修改 orchestrator 行为。

5. **测试的行为断言必须保持不变或更清晰**
   - `test_missing_channel.sh` 仍需断言缺失 channel 时的 fatal startup 行为；
   - `test_missing_force_replan.sh` 仍需断言缺失 `--force-replan` 参数时的 fatal startup 行为；
   - `test_orchestrator_logs.sh` 仍需断言 `.tmp/sdlc_logs` 和关键 debug/log scan 线索存在。

### Non-Functional Requirements

1. **测试必须 self-contained**
   - 同一份脚本在作者本地与 GitHub hosted runner 上应有一致的基本初始化能力。

2. **不得通过削弱断言来“修绿”**
   - 不能把 startup fatal contract 改得更宽松；
   - 不能通过跳过关键日志检查或吞掉初始化失败来掩盖问题。

3. **blast radius 必须最小**
   - 首选修改测试脚本本身；
   - 避免顺手改动无关 orchestrator 逻辑。

### User Stories

- **As a maintainer**, I want clean-runner failures in orchestrator bash tests to reflect real product/test contract problems, not missing git identity setup in sandbox repos.
- **As a reviewer**, I want these tests to be self-contained so a local pass and a GitHub-hosted runner pass mean the same thing.
- **As an operator**, I want startup/contract test failures to diagnose orchestrator behavior directly, not be polluted by unrelated sandbox bootstrap assumptions.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **test-harness-first repair** 策略。

### 3.1 核心设计原则

1. **先修 sandbox contract，再怀疑 orchestrator 主逻辑**
   - 这组失败的第一嫌疑点是测试初始化依赖；
   - 只有在 clean sandbox contract 自洽之后，剩余失败才应被解释为真正的 orchestrator 行为问题。

2. **repo-local git identity 优先于宿主机 global identity**
   - 测试必须显式配置临时 repo 所需的最小 git identity，或采用等价方案；
   - 不应假设 `git commit` 能从开发者机器环境里继承用户配置。

3. **clean-runner parity 要可验证**
   - 测试设计本身必须能证明：即使无 global git config，也能继续走到目标验证路径。

### 3.2 推荐实现路径

建议优先检查并最小修复以下脚本：
- `scripts/test_missing_channel.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`

优先修复方向：
1. 在每个临时 repo `git init` 之后、第一次 `git commit` 之前，显式设置最小 repo-local git identity；
2. 如有必要，引入额外隔离（例如限制对宿主机 global git config 的依赖）来保证 clean-runner parity；
3. 保持原有行为断言；
4. 只有在 harness 修正后仍失败时，再分析是否需要改 orchestrator 本体。

### 3.3 允许修改的范围

本 PRD 允许修改：
- `/home/openclaw/projects/leio-sdlc/scripts/test_missing_channel.sh`
- `/home/openclaw/projects/leio-sdlc/scripts/test_missing_force_replan.sh`
- `/home/openclaw/projects/leio-sdlc/scripts/test_orchestrator_logs.sh`
- 与上述测试 clean-runner parity directly relevant 的最小 supporting test helpers（如确有必要）

本 PRD 不授权：
- 大规模重构 orchestrator 主逻辑；
- 同时修复无关 pytest / mocked E2E / PR-003 regressions；
- 通过放宽断言、吞错误、或绕过 startup contract 来让测试变绿。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Missing-channel test is self-contained on a clean sandbox repo**
  - **Given** a temporary git repo with no reliance on pre-existing global git identity
  - **When** `scripts/test_missing_channel.sh` initializes the repo and invokes orchestrator without `--channel`
  - **Then** the test reaches the orchestrator startup validation path
  - **And** it fails for the intended missing-channel reason rather than sandbox git-commit setup failure

- **Scenario 2: Missing-force-replan test is self-contained on a clean sandbox repo**
  - **Given** a temporary git repo with no reliance on pre-existing global git identity
  - **When** `scripts/test_missing_force_replan.sh` initializes the repo and invokes orchestrator without `--force-replan`
  - **Then** the test reaches the orchestrator startup validation path
  - **And** it fails for the intended missing-force-replan reason rather than sandbox git-commit setup failure

- **Scenario 3: Orchestrator log test reaches log creation and scan trace path on a clean sandbox repo**
  - **Given** a temporary git repo with no reliance on pre-existing global git identity
  - **When** `scripts/test_orchestrator_logs.sh` initializes the repo and runs orchestrator in test mode
  - **Then** `.tmp/sdlc_logs` is created
  - **And** an `orchestrator_*.log` file exists
  - **And** the expected scan/debug line (such as `Scanning job_dir`) is present when the orchestrator path is exercised

- **Scenario 4: Local and GitHub-hosted execution agree on the initialization contract**
  - **Given** the repaired bash sandbox tests
  - **When** they are run on a developer machine and on a clean GitHub-hosted runner
  - **Then** neither environment requires preconfigured host-level git identity for the tests to enter their target validation paths

- **Scenario 5: The fix does not weaken the intended startup/logging assertions**
  - **Given** the repaired tests
  - **When** they pass
  - **Then** the pass condition still demonstrates the intended orchestrator startup/logging contract, not merely successful sandbox initialization

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是“git commit 在 CI 上挂了一次”，而是：

1. 测试对宿主机环境有隐藏依赖，导致本地绿、CI 红；
2. 修复时只让 `git commit` 能过，但没有保证测试真正进入目标 orchestrator 验证路径；
3. 为了快速变绿而削弱 startup/logging 断言，造成假修复。

### Verification Strategy

#### A. Script-level self-containment verification
需要验证：
- 每个 bash sandbox test 在临时 repo 中都能自给自足地完成最小初始化；
- 不依赖预置 global git identity。

#### B. Clean-runner parity verification
需要显式覆盖：
- 无 global git config 条件下的本地执行；
- GitHub-hosted runner 执行。

本地验证不能只依赖开发者默认机器环境；如有必要，应通过隔离 `HOME` 或等价手段确认 tests 不吃宿主机配置。

#### C. Behavior-preservation verification
需要验证：
- `test_missing_channel.sh` 仍断言 `[FATAL_STARTUP]` 和 missing channel message；
- `test_missing_force_replan.sh` 仍断言 `[FATAL_STARTUP]` 和 missing `--force-replan` message；
- `test_orchestrator_logs.sh` 仍断言日志目录和关键扫描日志存在。

### Quality Goal
本 PRD 的质量目标不是单纯“让几支脚本在 CI 绿掉”，而是：

> **让 orchestrator startup/logging bash tests 成为真正 self-contained、clean-runner-safe 的 contract tests，使它们在本地和 GitHub-hosted runner 上都能先稳定进入目标验证路径，再对 orchestrator 行为作出可信断言。**

## 6. Framework Modifications (框架防篡改声明)
- `/home/openclaw/projects/leio-sdlc/scripts/test_missing_channel.sh`
- `/home/openclaw/projects/leio-sdlc/scripts/test_missing_force_replan.sh`
- `/home/openclaw/projects/leio-sdlc/scripts/test_orchestrator_logs.sh`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 #25 / #30 视为纯 orchestrator 产品逻辑故障，直接从业务路径入手。
- **Observed correction**: 失败首先表现为 clean-runner sandbox repo 初始化对宿主机 git identity 的隐式依赖，因此需要先修测试 harness 自洽性。
- **v2.0 Revision Rationale**: 采用 test-harness-first repair，先建立 clean-runner-safe sandbox contract，再判断剩余 orchestrator 行为问题。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`missing_channel_error_substring`**:
```text
Missing channel parameter
```

- **`missing_force_replan_error_substring`**:
```text
Missing required parameter: --force-replan
```

- **`fatal_startup_marker`**:
```text
[FATAL_STARTUP]
```

- **`log_scan_marker`**:
```text
Scanning job_dir
```
