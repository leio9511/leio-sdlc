---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 41 Planner Side Effects Mock Contract Alignment

## 1. Context & Problem (业务背景与核心痛点)
在 issue #40 的 suite contamination 问题与 issue #41 的 clean-runner mock contract 问题拆分后，已经可以确认：

- issue #40 的核心污染链路是测试环境变量未恢复，属于 suite 级隔离问题；
- issue #41 则是另一类完全不同的失败：**mock-based orchestrator tests 在宣称“planner 成功执行”的同时，没有补齐 planner 成功后的文件系统 side effects。**

当前在 GitHub Actions `Preflight`、clean runner、以及 clean worktree 场景中，以下类型测试会暴露这一问题：

- `tests/test_thinking_e2e_convergence.py`
- `tests/test_thinking_orchestrator_primary.py`
- `tests/test_orchestrator_session_strategy.py`
- 以及其它使用类似 orchestrator mock 模式的测试

这些测试通常会：
- patch `orchestrator.dpopen`
- 让 `spawn_planner.py` 对应的 fake process 返回成功
- 然后断言 orchestrator 后续行为

但真实 orchestrator 的 contract 并不是“planner subprocess returncode == 0 就算成功”。在 planner 返回后，orchestrator 还会继续依赖 planner 产物，例如：

- `job_dir` 必须存在
- `job_dir/*.md` 必须存在至少一个 PR slice
- 某些路径下还会依赖 run anchor / manifest / queue 状态

当前这类测试的核心缺陷是：

> **它们 mock 了 planner 成功，却没有 mock planner 成功后应当产生的 side effects，因此在 clean runner 上会触发 `.sdlc_runs/.../dummy` / `job_dir` / `*.md` 相关失败。**

这类失败并不说明 orchestrator 的生产逻辑损坏。相反，它说明：

- 测试对 planner-success contract 的建模不完整；
- 本地环境中偶然存在的目录、历史残留、工作树状态，有时掩盖了问题；
- GitHub clean runner 把这种“returncode 成功但产物缺失”的假设漏洞稳定暴露出来。

本 PRD 的目标是：

> **把所有“mock planner success”的 orchestrator tests 调整为 contract-complete：只要测试宣称 planner 成功，就必须同时提供 planner 成功后的最小必要 side effects。**

本 PRD 不处理：
- issue #40 的 suite contamination / `SDLC_TEST_MODE` 环境恢复问题；
- deploy/rollback tests 相关失败（已独立追踪为 issue #42）；
- 生产 orchestrator 逻辑改薄或绕过 guardrail 的方案。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须把 planner success 的测试 contract 定义完整**
   - 任何测试如果 mock `dpopen(spawn_planner.py)` 成功返回，且其语义上表示“planner 成功完成”，则测试必须同时模拟 planner 成功后的最小产物：
     - `job_dir` 存在
     - `job_dir` 下至少存在一个可被 orchestrator 扫描到的 `*.md` PR slice
   - 如果对应测试路径还依赖其它 planner side effects，则也必须在测试中显式提供。

2. **必须优先修测试，而不是改产品逻辑迎合测试**
   - 不允许删除 orchestrator 对 `job_dir` / `*.md` 的后置校验；
   - 不允许为了让测试通过而放宽“planner 成功必须有产物”的生产 contract；
   - 不允许通过跳过真实状态检查来掩盖 mock 不完整问题。

3. **必须让 clean runner 与本地验证一致**
   - 修复后，相关测试在本地 clean worktree / worktree 中与 GitHub Actions clean runner 上都必须一致；
   - 不允许继续依赖主工作区已有 `.sdlc_runs`、历史生成目录、或其它偶然残留。

4. **必须收敛 issue #41 对应的测试文件范围**
   - 至少覆盖当前已知相关测试：
     - `tests/test_thinking_e2e_convergence.py`
     - `tests/test_thinking_orchestrator_primary.py`
     - `tests/test_orchestrator_session_strategy.py`
   - 如有其它相同模式测试，也应一并纳入修复范围，但仅限 planner-success side-effect contract 问题。

### Non-Functional Requirements

1. **blast radius 必须可控**
   - 只改测试 / 测试辅助 helper / fixture；
   - 不修改 orchestrator 生产逻辑本身；
   - 不和 #40 / #42 混修。

2. **测试语义必须更清晰，而不是更魔法**
   - 看到测试时，应能一眼看出：
     - 当前在 mock planner 成功
     - 对应伪造了哪些 planner 产物
   - 不要依赖隐藏的全局 fixture 在背后偷偷造目录，让测试语义变黑箱。

3. **可复用 helper 优先于重复散落的手工造假**
   - 如多个测试都需要相同的 planner-success 假产物，应抽取共享 helper；
   - 避免每个测试重复手写略有差异的“半套 side effects”，再次埋下不一致风险。

### User Stories

- **As a maintainer**, I want planner-success mock tests to model the full minimal success contract, so CI failures reflect real regressions instead of incomplete mocks.
- **As a reviewer**, I want clean-runner failures to be fixed in the test layer rather than by weakening runtime checks, so orchestrator safety remains intact.
- **As an engineer**, I want all orchestrator tests that mock planner success to explicitly create the expected fake artifacts, so local, worktree, and GitHub CI runs behave consistently.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **contract-complete fake planner side effects** 方案：

- 保持 orchestrator 生产 contract 不变；
- 在测试层补齐 planner success 对应的文件系统 side effects；
- 尽量通过共享 helper 抽象最小成功产物；
- 以 clean worktree / GitHub runner 一致通过为最终质量目标。

### 3.1 核心设计决策

1. **planner success 不等于 subprocess returncode 0**
   - 在 orchestrator 当前设计里，planner success 的黑盒含义是：
     - spawn_planner 被调用并返回成功
     - 下游 `job_dir` 存在
     - 至少一份 PR contract markdown 被落盘
   - 因此测试必须反映这一点，而不能只 mock 一个成功进程对象。

2. **优先引入共享 helper 来伪造 planner 产物**
   - 推荐在测试文件内部或共享测试 helper 中提供类似能力：
     - `seed_fake_job_dir(...)`
     - `seed_fake_pr_slice(...)`
     - `make_fake_planner_success(...)`
   - helper 的职责是：在测试 workdir / global_dir 里创建 orchestrator 期待看到的最小目录结构和 PR markdown。

3. **路径应按 orchestrator 当前真实规则计算，而不是手写猜测**
   - helper 不应拍脑袋拼路径；
   - 应按当前 orchestrator 使用的规则构造：
     - `job_dir = <global_dir>/.sdlc_runs/<project_name>/<prd_name_without_ext>`
   - 这样测试才能和生产 contract 严格对齐。

4. **本 PRD 不接受“放宽 orchestrator 后置检查”作为修复方式**
   - 如果 planner 成功却没有 `job_dir` / `*.md`，生产逻辑本来就应该判失败；
   - 测试要学会尊重这个 contract，而不是要求产品为了测试变得更宽松。

### 3.2 推荐实现方向

#### A. Add a minimal planner-success helper
至少提供以下行为之一：
- 直接在目标测试文件里加入 helper
- 或提取到测试共享模块中

helper 应该完成：
- 创建 `job_dir`
- 写入至少一个最小合法 `PR_001_*.md` 或等价 slice 文件
- 如有需要，补 run manifest / baseline 文件，但仅限被测试路径真正依赖的最小集合

#### B. Update affected tests to use the helper
重点修复：
- `tests/test_thinking_e2e_convergence.py`
- `tests/test_thinking_orchestrator_primary.py`
- `tests/test_orchestrator_session_strategy.py`

这些测试中，凡是 mock planner success 的地方，都要调用 helper 造 side effects。

#### C. Keep other mocks narrow
仍然允许：
- mock `dpopen`
- mock `drun`
- mock `notify_channel`
- mock handshake / test-mode 路径

但这些 mocks 不再被允许替代 planner artifact contract。

#### D. Validate in clean worktree
修复后的验证必须在干净 worktree 或临时路径中执行，避免主工作区残留再次掩盖问题。

### 3.3 明确不采用的方案

1. **不通过修改 orchestrator 产品逻辑来迎合测试**
   - 不删除 `job_dir` 存在性检查；
   - 不删除 `*.md` 检查；
   - 不把 planner success 判定弱化成“进程返回 0 就算成功”。

2. **不继续依赖偶然的本地残留目录**
   - 不接受“在我的机器上能过就行”；
   - clean runner 和 clean worktree 的结果必须成为主标准。

3. **不把 #41 和 #42 混修**
   - deploy / rollback tests 另有独立 issue；
   - 本 PRD 只处理 orchestrator mock planner side effects。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: mock planner success includes required planner artifacts**
  - **Given** an orchestrator test that mocks `spawn_planner.py` as successful
  - **When** the orchestrator proceeds beyond the planner spawn step
  - **Then** the test also provides a valid `job_dir`
  - **And** the test also provides at least one PR markdown slice visible to the orchestrator

- **Scenario 2: relevant thinking/orchestrator tests pass in clean environments**
  - **Given** the known tests tracked by issue #41
  - **When** they run in a clean worktree / clean runner environment
  - **Then** they no longer fail due to missing `.sdlc_runs/.../dummy` / `job_dir` / planner artifact paths

- **Scenario 3: orchestrator runtime contract remains unchanged**
  - **Given** the orchestrator’s planner-success validation logic
  - **When** the fix is implemented
  - **Then** the production code still requires planner artifacts after planner success
  - **And** the fix is achieved by improving tests rather than weakening runtime checks

- **Scenario 4: issue #41 targeted tests become stable on GitHub CI**
  - **Given** GitHub Actions `Preflight` workflow
  - **When** the issue #41 fix is merged
  - **Then** the tests previously failing because of planner side-effect mock incompleteness pass on the clean GitHub runner

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本 PRD 的最大风险不是“helper 写不出来”，而是：

1. 用一个更大的全局 fixture 隐式造目录，虽然 CI 绿了，但测试语义继续模糊；
2. 顺手把 orchestrator 生产逻辑改薄，让假测试过关；
3. 只修当前 1~2 个失败用例，没有把同模式测试一起收敛，后面继续冒红；
4. 只在本地当前工作区绿，clean runner 仍然红。

### Verification Strategy

#### A. Focused test verification
至少显式运行：
- `pytest -q tests/test_thinking_e2e_convergence.py`
- `pytest -q tests/test_thinking_orchestrator_primary.py`
- `pytest -q tests/test_orchestrator_session_strategy.py`

#### B. Clean-worktree verification
建议在独立临时 worktree 中运行：
- `pytest tests/`

重点观察 issue #41 相关失败是否消失。

#### C. GitHub CI verification
必须通过：
- GitHub Actions `Preflight`

因为 #41 的主要暴露面就是 clean GitHub runner。

#### D. Out-of-scope discipline
如全量 pytest 仍有 deploy/rollback 失败，不应把这些归咎于本 PRD；它们属于 #42。

## 6. Framework Modifications (框架防篡改声明)
本 PRD 允许修改以下文件（仅限测试层 / 测试辅助层）：
- `tests/test_thinking_e2e_convergence.py`
- `tests/test_thinking_orchestrator_primary.py`
- `tests/test_orchestrator_session_strategy.py`
- 与 planner side-effect mock helper 直接相关的测试辅助文件

本 PRD **不授权**修改：
- `scripts/orchestrator.py`
- `scripts/agent_driver.py`
- `scripts/utils_notification.py`
- 任何生产逻辑中的 planner success 判定 / guardrail / artifact 后置检查

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初版将 #41 定义为 GitHub clean runner 上 orchestrator/thinking mock tests 因 planner side effects 缺失而失败的问题。
- **v1.1 Scope Decision**: 明确采用“补齐 fake planner side effects”方案，不改 orchestrator 产品逻辑。
- **v1.2 Boundary Clarification**: 与 #40（suite contamination）和 #42（deploy/rollback tests）彻底拆分，避免混修。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
