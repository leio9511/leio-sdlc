---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 40 Test Suite Contamination Isolation Repair

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前的 GitHub `Preflight` / 本地 `preflight.sh --report-all` 质量门依赖 pytest 全量套件具备稳定、可重复、与执行顺序无关的行为。但在 issue #40 中暴露出一个典型的 suite 级污染问题：

- `tests/test_thinking_orchestrator_primary.py` 与 `tests/test_thinking_e2e_convergence.py` 单独运行时可以通过；
- 但当它们在全量 `pytest tests/` 中排在 `tests/test_spawn_auditor.py` 之后运行时，会稳定失败；
- 失败并不是因为 orchestrator / thinking contract 的产品逻辑直接损坏，而是因为前序测试修改了进程级环境变量后没有恢复，污染了后序测试的运行环境；
- 结果导致后续 thinking/orchestrator 测试在“是否处于 `SDLC_TEST_MODE`”这一运行前提上拿到错误值，进而进入错误的 notification / ignition 分支。

已经确认的关键污染链路如下：

1. `tests/conftest.py` 在 pytest session 启动时设置 `SDLC_TEST_MODE = "true"`，作为测试会话默认值；
2. `tests/test_spawn_auditor.py` 中多个测试直接使用 `os.environ["SDLC_TEST_MODE"] = "false"` 或其它直接赋值方式覆盖该值；
3. 这些修改没有通过 `monkeypatch`、`patch.dict` 或显式恢复逻辑清理，因而跨测试保留；
4. thinking/orchestrator 测试随后运行时读取到了错误的 `SDLC_TEST_MODE`，不再走测试隔离路径，而进入真实 notification/handshake 路径，最终产生与测试意图不一致的失败。

这个问题的本质不是“某个单测坏了”，而是：

> **测试套件自身未能维持环境隔离 contract，导致运行顺序影响结果，从而让 preflight/CI 失去可信度。**

本 PRD 的目标是只解决 issue #40：

> **修复 suite 级环境污染，恢复 thinking/orchestrator 测试在“单跑、组合跑、全量跑”三种模式下的一致行为。**

本 PRD 不负责解决另一类已经单独记录的 CI 失败：
- issue #41：mock-based orchestrator tests 在 GitHub clean runner 上因 `.sdlc_runs/.../dummy` / planner 产物 side effect 建模不完整而失败；
- 该问题必须在独立 PRD 中处理，不与本 PRD 混在一起。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须消除 `test_spawn_auditor.py` 对后续测试的环境变量污染**
   - 任何测试中对 `SDLC_TEST_MODE`、`MOCK_AUDIT_RESULT`、`SDLC_RUN_DIR` 等进程级环境变量的修改，都必须在测试结束后恢复；
   - 不允许继续通过裸写 `os.environ[...] = ...` 的方式制造跨测试残留；
   - 允许使用：
     - `pytest` 的 `monkeypatch`
     - `unittest.mock.patch.dict`
     - 或等价的显式恢复 fixture / helper
   - 但恢复行为必须是自动且可审计的，不能依赖人工记得清理。

2. **必须恢复相关 thinking/orchestrator 测试的顺序无关性**
   - `tests/test_thinking_orchestrator_primary.py` 与 `tests/test_thinking_e2e_convergence.py` 在以下三种模式下都必须表现一致：
     - 单文件独立运行
     - 与 `tests/test_spawn_auditor.py` 组合运行
     - 全量 `pytest tests/` 运行
   - 不允许再出现“单跑通过、全量失败”的 order-dependent 行为。

3. **本 PRD 只修 suite contamination，不改写产品逻辑来迎合测试**
   - 不允许通过削弱 orchestrator 的 handshake / notification / guardrail 产品逻辑来让测试通过；
   - 不允许通过绕过真实运行时 contract 来掩盖污染问题；
   - 问题应在测试层解决，而不是把生产逻辑改薄。

4. **必须把修复范围限制在 #40 的隔离问题**
   - 本 PRD 不处理 #41 的 planner side effect / `.sdlc_runs/.../dummy` CI 问题；
   - 不要求在本 PRD 中清空 `ignore_tests.json`；
   - 不要求在本 PRD 中完成 GitHub CI 全绿收口；
   - 如果修复 #40 后仍有 #41 留存，这是符合预期的。

### Non-Functional Requirements

1. **修复必须低 blast radius**
   - 优先修改测试文件、测试辅助 fixture、或测试专用 helper；
   - 不要顺手重构 orchestrator 主流程；
   - 不要把两个 issue 的修复混在一个提交/PRD 里。

2. **测试意图必须保持清晰**
   - 修复污染时不能让测试语义模糊；
   - 不能因为增加一个全局兜底 fixture，就让后续测试继续无约束地裸写环境变量而不被注意；
   - 优先保留“谁修改环境，谁恢复环境”的局部可读性。

3. **验证结论必须可重复**
   - 不能只给出一次偶然绿灯；
   - 必须通过组合跑和全量跑证明顺序依赖已消失。

### User Stories

- **As a maintainer**, I want pytest session state to remain isolated across tests, so preflight and CI results do not depend on test ordering.
- **As a reviewer**, I want issue #40 fixed in the test layer rather than hidden by product-logic weakening, so CI trust is restored without runtime regression risk.
- **As an engineer**, I want `test_spawn_auditor.py` and thinking/orchestrator tests to have explicit, self-contained environment setup/teardown, so their behavior is deterministic in single-run, combo-run, and full-suite contexts.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **test-layer isolation repair** 路线，而不是产品逻辑绕行：

- 把 suite contamination 当成测试环境 contract 失效来修；
- 将修复限制在测试层（测试文件、测试 fixture、测试 helper）；
- 保持 orchestrator / notification / handshake 的生产逻辑不变；
- 用组合跑和全量跑证明污染被消除。

### 3.1 核心设计决策

1. **以局部恢复为优先，不靠“黑盒全局兜底”掩盖问题**
   - 最推荐的手法是：
     - 在具体测试里用 `monkeypatch.setenv(...)`
     - 或 `patch.dict(os.environ, {...}, clear=False)`
   - 这样可以明确看到：哪个测试需要什么环境，测试结束后如何恢复。

2. **允许存在最小化的测试会话兜底恢复，但不能替代局部修复**
   - 如果有必要，可以在测试文件内增加轻量 fixture 用于恢复 `SDLC_TEST_MODE` 到 `conftest.py` 的默认值；
   - 但这种 fixture 只能作为保险丝，不应该成为继续裸写 `os.environ[...]` 的借口。

3. **不修改 orchestrator 正常运行时逻辑**
   - 不删减 ignition handshake；
   - 不把 notification provider 改成只为测试静默；
   - 不修改真实 SDLC runtime 行为来迁就 order-dependent tests。

4. **本 PRD 的 done 定义是“污染消失”，不是“所有 related CI failure 全部清零”**
   - #40 的收口标准是：suite contamination 消失；
   - 如果 #41 仍然存在，那应该作为后续独立问题处理，不属于本 PRD 失败。

### 3.2 推荐实现方向

#### A. Test env writes must become reversible
重点检查并修复：
- `tests/test_spawn_auditor.py`
- 以及任何其它直接裸写 `os.environ[...]` 且无恢复逻辑的相关测试

推荐替换模式：
- `os.environ["KEY"] = "value"`
- 替换为：
  - `monkeypatch.setenv("KEY", "value")`
  - 或 `with patch.dict(os.environ, {"KEY": "value"}, clear=False): ...`

#### B. Preserve conftest default as baseline
- `tests/conftest.py` 中的 `SDLC_TEST_MODE = "true"` 作为 suite baseline 可以保留；
- 但任何测试临时覆盖后，必须恢复到该 baseline；
- 不允许让覆盖值泄漏到后序测试。

#### C. Verification must include combo runs
不能只跑：
- `pytest tests/test_thinking_orchestrator_primary.py`
- `pytest tests/test_thinking_e2e_convergence.py`

还必须至少覆盖：
- `pytest tests/test_spawn_auditor.py tests/test_thinking_e2e_convergence.py`
- `pytest tests/test_spawn_auditor.py tests/test_thinking_orchestrator_primary.py`
- `pytest tests/`

#### D. Explicitly exclude #41 work
本 PRD 明确不做：
- `.sdlc_runs/.../dummy` 路径 / planner side effect mock 修复；
- `.dist` / GitHub runner clean-env planner artifact modeling；
- `ignore_tests.json` 清空与否的最终收口。

### 3.3 明确不采用的方案

1. **不通过削弱 orchestrator 逻辑来让测试通过**
   - 不删除 / 绕过 handshake；
   - 不把 notification 逻辑改成对 test channel 永远静默；
   - 不牺牲运行时 guardrail 换测试绿灯。

2. **不把 #40 和 #41 合并修复**
   - #40 是 suite contamination；
   - #41 是 planner success side-effect mocking；
   - 两者边界必须清晰。

3. **不依赖“重新加 ignore”作为交付**
   - 这会再次把真实问题藏回去；
   - 本 PRD 的目标是修污染，不是重新隔离失败测试。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: `test_spawn_auditor.py` no longer contaminates subsequent tests**
  - **Given** pytest session baseline sets `SDLC_TEST_MODE = "true"`
  - **When** `tests/test_spawn_auditor.py` runs before other orchestrator/thinking tests
  - **Then** later tests still observe the expected baseline test-mode behavior rather than a leaked override value

- **Scenario 2: thinking/orchestrator tests become order-independent**
  - **Given** the thinking/orchestrator test files relevant to issue #40
  - **When** they run individually, in combination with `tests/test_spawn_auditor.py`, and in the full suite
  - **Then** they produce the same pass/fail outcome in all three modes
  - **And** they no longer fail only because `tests/test_spawn_auditor.py` ran earlier

- **Scenario 3: issue #40 is fixed without weakening runtime logic**
  - **Given** the orchestrator notification / handshake / guardrail behavior
  - **When** the fix is implemented
  - **Then** the production runtime paths remain unchanged
  - **And** the repair is achieved through test-layer isolation handling rather than product-logic bypass

- **Scenario 4: full local pytest suite reflects the removal of suite contamination**
  - **Given** the local repository test suite
  - **When** `pytest tests/` is executed after the fix
  - **Then** the specific order-dependent failures tracked by issue #40 no longer appear

- **Scenario 5: issue #41 remains out of scope**
  - **Given** planner artifact / `.sdlc_runs/.../dummy` failures tracked separately
  - **When** this PRD is executed
  - **Then** the implementation is not required to fix them
  - **And** the PRD is still considered successful if suite contamination is removed but #41 remains for later work

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本 PRD 最大风险不是“修不出绿灯”，而是：

1. 用一个粗暴的全局兜底把污染暂时遮住，却没有修掉具体违规测试；
2. 为了让测试通过而偷偷改薄 orchestrator 运行时逻辑；
3. 把 #40 和 #41 混修，导致验收边界不清；
4. 只在单文件上验证通过，却没有证明 suite 级顺序依赖已经消失。

### Verification Strategy

#### A. Focused combo verification
必须显式运行并观察：
- `pytest -q tests/test_spawn_auditor.py`
- `pytest -q tests/test_thinking_e2e_convergence.py`
- `pytest -q tests/test_thinking_orchestrator_primary.py`
- `pytest -q tests/test_spawn_auditor.py tests/test_thinking_e2e_convergence.py`
- `pytest -q tests/test_spawn_auditor.py tests/test_thinking_orchestrator_primary.py`

#### B. Full-suite verification
必须运行：
- `pytest tests/`

#### C. Preflight verification
建议运行：
- `bash preflight.sh --report-all`

但这里的结果只用于确认 #40 是否已不再产生“suite contamination”症状，**不强制要求把 #41 一并修掉**。

#### D. Mock discipline
- 不新增 live LLM 依赖；
- 不把本 PRD 变成真实 notification / gateway integration 修复；
- 重点是验证环境恢复和顺序无关性，而不是通知通道本身。

## 6. Framework Modifications (框架防篡改声明)
本 PRD 允许修改以下测试/测试辅助文件（仅限解决 issue #40）：
- `tests/test_spawn_auditor.py`
- `tests/conftest.py`（如确有必要，但仅限测试环境恢复语义）
- 与 issue #40 直接相关的测试 helper / fixture 文件

本 PRD **不授权**修改以下内容来规避问题：
- `scripts/orchestrator.py`
- `scripts/agent_driver.py`
- `scripts/utils_notification.py`
- 任何生产运行时 notification / handshake / guardrail 逻辑

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初版把 #40 定义为“thinking/orchestrator 测试在全量 suite 中失败”的 order-dependent contamination 问题。
- **v1.1 Scope Decision**: 明确将 #40 与 #41 分离；#40 仅处理 suite 级环境污染，不处理 planner artifact mock / `.sdlc_runs/.../dummy` clean-runner 失败。
- **v1.2 Boundary Clarification**: 明确禁止通过修改 orchestrator 生产逻辑来让测试通过；修复必须发生在测试层。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
