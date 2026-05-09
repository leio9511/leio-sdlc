---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Handoff Test Run-Anchor Contract Cleanup and Unquarantine

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前的 clean-runner pytest failure surface 已经从早先的仓库根路径硬编码问题继续收缩，但仍有一类明确剩余问题：部分 handoff/orchestrator 测试仍然建立在**过时的 fake workdir / run-anchor 假设**上，导致这些测试一旦被真实执行，就在进入目标断言之前先因 `.sdlc_runs` / dummy job-dir 创建失败而中断。

当前已确认的两个核心测试文件是：

1. `tests/test_handoff_integration.py`
2. `tests/test_orchestrator_handoff.py`

这两个文件目前共享同一种旧测试模式：
- 使用 `args.workdir = "/dummy"`
- 使用 `args.job_dir = "docs/PRs/dummy"`
- 仅用非常薄的 `os.path.exists` / `glob.glob` mock 假装环境存在
- 但当前 `orchestrator.main()` 已经会在 `ensure_run_anchors()` 中真实执行 run-anchor 创建，例如 `os.makedirs(job_dir, exist_ok=True)`

结果是，这两个测试在单独执行时稳定暴露出同一类失败：
- `FileNotFoundError: '/dummy/.sdlc_runs'`
- `FileNotFoundError: '/dummy/.sdlc_runs/dummy/dummy'`

这说明它们当前失败的第一层 root cause 不是产品 handoff 逻辑本身，而是：

> **测试环境模拟没有和当前 orchestrator 的 run-anchor contract 对齐。**

另一个重要事实是：这两个测试目前仍在 `ignore_tests.json` 的 pytest ignore 列表中。因此：
- 本地全量 `preflight.sh --report-all` 虽然是绿的
- 但并不能说明这两个测试已经可用
- 因为它们根本没有被纳入 preflight 执行面

本 PRD 的目标不是清理整个 pytest suite，也不是处理 handoff 之外的其它 orchestrator debt，而是：

> **修复这两个 handoff/orchestrator 测试对 fake workdir / `.sdlc_runs` anchor 的过时假设，使它们在 focused 验证中真实通过，并在通过后把它们从 preflight ignore list 中放出来。**

本 PRD 不覆盖：
- broader pytest suite 里的其它失败（例如 agent-driver argv drift、spawn_auditor 相关问题等）
- PRD/docs/history artifacts
- GitHub-hosted witness / manual proof / branch promotion
- handoff 产品逻辑大重构，除非测试层修复被证明不足以对齐当前 contract

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须修复 `tests/test_handoff_integration.py` 与 `tests/test_orchestrator_handoff.py` 的 run-anchor 测试环境假设**
   - 不得继续依赖 `/dummy` 这类不可写、不可创建 `.sdlc_runs` 目录的 fake workdir 作为主测试环境；
   - 这两个测试必须在一个与当前 orchestrator 运行 contract 对齐的最小可用 workspace / global-dir / run-anchor 环境中执行；
   - 修复后，测试应能进入并验证其原本要验证的 handoff/orchestrator 行为，而不是提前死在目录创建阶段。

2. **优先通过真实 temp workspace 或同等强度的完整环境模拟来修复**
   - 推荐使用 `tempfile.TemporaryDirectory()`、真实 `workdir/.git`、真实 `global_dir`、以及可创建的 `.sdlc_runs` anchor 路径；
   - 若使用 mock 替代真实文件系统，必须完整覆盖 `ensure_run_anchors()` 所依赖的路径创建 contract，而不是只补一个零散的 `exists` 假设；
   - 不得通过换一个新的假绝对路径来掩盖问题。

3. **修复后必须保留测试原始业务意义**
   - `test_planner_failure` 仍然必须验证 planner 失败路径下的 handoff/orchestrator 行为；
   - `test_queue_empty` 仍然必须验证 queue-empty / UAT-failure 路径；
   - 不允许把测试降级成仅验证“目录能创建”或“文件存在”。

4. **必须在 focused 通过后再解除 quarantine**
   - 这两个测试在修复完成后，必须先通过 focused pytest 验证；
   - 只有当 focused 验证通过，才允许从 `ignore_tests.json` 的 pytest ignore 列表中移除：
     - `tests/test_handoff_integration.py`
     - `tests/test_orchestrator_handoff.py`
   - 不允许在 focused 仍失败时提前 unquarantine。

5. **必须增加一个回归保护，防止修好的 handoff/orchestrator tests 被悄悄重新 quarantine**
   - 可以通过新增或扩展一个 repository-local manifest contract test 来显式断言上述两个测试不再处于 pytest ignore 列表中；
   - 该回归保护必须同时验证 manifest 至少具备合法 shape，避免通过 malformed JSON 假装“没忽略”。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 优先只修改：
     - `tests/test_handoff_integration.py`
     - `tests/test_orchestrator_handoff.py`
     - `ignore_tests.json`
     - 以及一个必要的 very narrow regression guard test / helper
   - 不应顺带重构整个 orchestrator test suite。

2. **focused verification 必须先于全量 preflight**
   - 这次工作的首要完成信号，不是“直接看全量 preflight 绿不绿”，而是先证明这两个测试文件本身已经完整通过；
   - 全量 preflight 只作为后续集成确认，而不是跳过 focused gate 的替代品。

3. **同类问题可以一起治理，但不得扩张到无关 pytest debt**
   - 当前允许同一轮处理这两个文件，因为它们共享同一类 root cause；
   - 但不得把范围扩大到 `tests/test_079_*`、`tests/test_083_*`、`tests/test_spawn_auditor.py` 或其它不属于 handoff run-anchor 假设的问题。

### User Stories

- **As a CI maintainer**, I want the handoff/orchestrator tests to run in a realistic temporary workspace contract, so clean-runner failures reflect real logic problems rather than fake-path setup debt.
- **As a reviewer**, I want the repaired handoff tests to be removed from quarantine only after they pass in focused validation, so preflight green remains truthful.
- **As an engineer**, I want a narrow fix that addresses only the shared `.sdlc_runs` / dummy-anchor failure mode, so the SDLC can converge without re-opening unrelated pytest cleanup.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **minimal realistic test environment alignment** 路线：
- 将这两个 handoff/orchestrator 测试从“假 `/dummy` + 不完整 mock”的模式迁移到“真实 temp workspace / global-dir / run-anchor”或同等强度的完整环境模拟；
- 先证明 focused 测试文件自身可以完整通过；
- 再解除 preflight ignore；
- 最后用回归保护锁定“不再被悄悄 quarantine”。

### 3.1 核心设计决策

1. **把当前失败归类为测试 contract 失配，而不是产品逻辑先验失败**
   - 现在最先爆炸的是 `.sdlc_runs` / dummy anchor 环境准备；
   - 在测试真实进入目标行为断言之前，这个环境债必须先清理。

2. **优先给测试一个最小真实 workspace，而不是继续给 `/dummy` 打补丁**
   - 当前 orchestrator 行为已经真实依赖 run-anchor 创建；
   - 因此继续围着 `/dummy` 修 `exists` mock 属于脆弱补丁，而不是稳定修复。

3. **如果引入 helper，helper 必须很小，只服务这同类测试**
   - 可以抽一个 very small shared helper，用于准备 temp `workdir` / `.git` / `global_dir`；
   - 但不应借机演变成测试基础设施重构项目。

4. **解除 quarantine 必须是后置动作，不是和代码修改并行赌博**
   - 当前这两个测试还在 ignore list 中；
   - 如果不先 focused 验证就直接 unquarantine，容易把已知红点直接注入 preflight 并导致 SDLC 不收敛；
   - 因此必须先 focused green，再 unquarantine。

### 3.2 推荐实现方向

#### A. `tests/test_handoff_integration.py`
- 用 temp workspace / real run-anchor setup 替代 `/dummy` 主路径；
- 让测试所需的 `workdir`、`global_dir`、job/run dir 结构与当前 orchestrator contract 一致；
- 保留对 planner failure、queue empty、dirty workspace 等行为的原始断言。

#### B. `tests/test_orchestrator_handoff.py`
- 与上面采用相同的环境准备模式；
- 不再依赖 fake absolute path + 稀疏 `exists` mock；
- 保留 handoff/orchestrator 行为断言本身。

#### C. Shared helper (optional but recommended)
- 若抽取 helper，应仅负责：
  - 创建 temp `workdir`
  - 创建 `workdir/.git`
  - 创建 temp `global_dir`
  - 返回与当前 orchestrator contract 对齐的最小路径结构
- 不应把断言逻辑抽成黑盒，避免测试可读性下降。

#### D. Unquarantine + regression guard
- focused green 后，从 `ignore_tests.json` 中移除：
  - `tests/test_handoff_integration.py`
  - `tests/test_orchestrator_handoff.py`
- 新增或扩展一个 manifest contract test，确保这两个文件不会重新进入 pytest ignore 列表。

### 3.3 明确不采用的方案

1. **不直接在 focused 失败状态下解除 quarantine**
   - 这只会把已知失败注入 preflight，扩大噪音。

2. **不通过 skip / xfail / weaken assertions 让测试看起来通过**
   - 这会破坏 handoff/orchestrator 测试的业务意义。

3. **不把这轮修复扩大成 broader pytest cleanup**
   - 当前 brief 只处理这两个 handoff/orchestrator 文件共享的 `.sdlc_runs` / dummy-anchor root cause。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Handoff integration test runs inside a valid temporary run-anchor environment**
  - **Given** a temporary workspace and global-dir structure aligned with the current orchestrator contract
  - **When** `tests/test_handoff_integration.py` is executed
  - **Then** it does not fail on `/dummy/.sdlc_runs` path creation
  - **And** it reaches and evaluates the intended handoff/planner/UAT assertions

- **Scenario 2: Orchestrator handoff test runs inside a valid temporary run-anchor environment**
  - **Given** a temporary workspace and global-dir structure aligned with the current orchestrator contract
  - **When** `tests/test_orchestrator_handoff.py` is executed
  - **Then** it does not fail on `.sdlc_runs` / dummy run-anchor setup
  - **And** it reaches and evaluates the intended orchestrator handoff assertions

- **Scenario 3: Focused validation passes before unquarantine**
  - **Given** the two targeted handoff/orchestrator test files have been repaired
  - **When** they are executed directly via focused pytest
  - **Then** the targeted files pass as a pair before any ignore-manifest removal is considered

- **Scenario 4: Repaired handoff tests are removed from the pytest ignore list only after they pass**
  - **Given** the focused validation for the two targeted test files is green
  - **When** `ignore_tests.json` is updated
  - **Then** `tests/test_handoff_integration.py` and `tests/test_orchestrator_handoff.py` are absent from the pytest ignore array
  - **And** unrelated quarantine entries remain untouched unless directly justified by the same requirement

- **Scenario 5: Regression protection prevents silent re-quarantine**
  - **Given** the repaired handoff/orchestrator tests have been unquarantined
  - **When** repository-local regression checks are run
  - **Then** they fail if either test is re-added to the pytest ignore manifest
  - **And** they also fail if the manifest is malformed in a way that would hide the regression

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
当前最大的风险不是“这两个测试现在红”，而是：

1. 测试环境模拟不真实，导致它们在进入目标断言前就因为 fake path / `.sdlc_runs` setup 债务而中断；
2. 修复后如果不先做 focused 验证就直接解除 quarantine，可能让 preflight 引入新的已知红点，导致 SDLC 不收敛；
3. 为了快速让 preflight 绿而弱化 handoff/orchestrator 行为断言。

### Verification Strategy

#### A. Focused file-level verification (mandatory first gate)
必须先验证：
- `pytest -q tests/test_handoff_integration.py tests/test_orchestrator_handoff.py`

只有这一步通过，才允许进入 unquarantine 阶段。

#### B. Manifest / quarantine regression verification
需要验证：
- 这两个测试从 `ignore_tests.json` 里移除；
- 回归保护会在它们被重新加入 ignore 时明确失败；
- unrelated quarantine entries 不会被顺手清空。

#### C. Preflight as post-fix integration confirmation
在 focused 通过并完成 unquarantine 后，再看 `bash ./preflight.sh --report-all` 是否继续保持 truthful signal；
如果 preflight 后续仍有失败，失败应属于下一层真实 pytest debt，而不是这两个 handoff/orchestrator 文件的 `.sdlc_runs` / dummy-anchor 问题。

### Quality Goal
本 PRD 的质量目标不是“一次解决整个 #26”，而是：

> **让这两个 handoff/orchestrator 测试从 fake `/dummy` 模式迁移到与当前 run-anchor contract 对齐的测试环境，并在 focused 通过后真实回归到 preflight 执行面。**

## 6. Framework Modifications (框架防篡改声明)
- `tests/test_handoff_integration.py`
- `tests/test_orchestrator_handoff.py`
- `ignore_tests.json`
- one narrow regression guard test or helper under `tests/` (only if needed)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 在 root-path portability subgroup 收敛后，#26 当前剩余 failure surface 进一步暴露出 handoff/orchestrator 测试中的 `.sdlc_runs` / dummy-anchor 问题。
- **v1.1 Evidence Tightening**: 单独运行 `tests/test_handoff_integration.py` 与 `tests/test_orchestrator_handoff.py`，确认当前失败面只暴露同一类 `FileNotFoundError`，没有第二类已知错误混入。
- **v1.2 Design Choice**: 决定把“修这两个测试”和“focused 通过后从 ignore list 放出来”放进同一 PRD，但明确 unquarantine 是后置动作而不是先手动作。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **For `ignore_tests.json` manifest key contract (must remain a top-level object using exactly these canonical keys):**
```text
bash
pytest
```

- **For the exact targeted pytest paths to remove from quarantine and protect against re-addition:**
```text
tests/test_handoff_integration.py
tests/test_orchestrator_handoff.py
```

- **For the focused validation command that must pass before unquarantine is allowed:**
```text
pytest -q tests/test_handoff_integration.py tests/test_orchestrator_handoff.py
```

