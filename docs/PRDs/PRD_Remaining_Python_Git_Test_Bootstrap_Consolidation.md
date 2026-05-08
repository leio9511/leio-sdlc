---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Remaining Python Git Test Bootstrap Consolidation

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 的前两波 git test bootstrap hardening 已经显著收缩了 clean-runner failure surface：
- bash / mocked E2E 路径已经建立并消费了 canonical git sandbox bootstrap contract；
- `scripts/test_pr_003.sh` 对应的 witness failure path 已经在真实 GitHub-hosted `Preflight` 上被推进过去；
- 第二波还在 `tests/conftest.py` 中引入了 Python-side shared contract `init_git_test_sandbox` / `git_test_sandbox` fixture，并成功迁移了 `tests/test_orchestrator_doctor.py`。

但是，真实 GitHub-hosted `Preflight` 仍然暴露出剩余 Python-side temp-repo bootstrap debt 并未完全收敛。

当前最明确的 CI witness 是：
- `tests/test_orchestrator_withdraw.py`
- fixture `repo_env(tmp_path)` / `repo_env_main(tmp_path)` 仍然通过 hand-rolled `git init` / `git add` / `git commit -m "init"` 建立测试仓库
- 在 clean runner 上，该路径暴露出 `git commit -m "init"` 的失败

这说明：
- Python-side shared helper 已经存在，但 repo 内仍有若干 pytest tests 没有迁入统一 contract；
- clean-runner parity 在 Python/pytest 面还没有最终闭环；
- 如果继续保留散点 `git init` / `git config` / baseline commit 逻辑，本地环境仍会掩盖这类问题，而 GitHub-hosted runner 会继续作为 truthful witness 把它们暴露出来。

本 PRD 的目标不是“修所有 pytest 问题”，也不是重构所有 Git 业务行为测试，而是：

> **把剩余 Python-side temp-repo bootstrap debt 收敛到 `tests/conftest.py` 中的 shared helper contract，消除这一类 clean-runner git identity/bootstrap failure，同时保持现有测试的业务断言与覆盖意图。**

本 PRD 不覆盖：
- 与 temp-repo bootstrap 无关的 pytest failures（例如路径硬编码、dummy-path contract drift、非 git portability 问题）；
- 通过新增 ignore list 条目、弱化断言、吞错误或 skip 测试来制造表面 green；
- 为了迁就过时测试而改动主逻辑或恢复已删除的产品 contract；
- 所有 git-dependent tests 的全面重写。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须以 `tests/conftest.py` 为唯一 canonical Python-side git bootstrap contract**
   - 对 Python / pytest 中需要创建 commit-capable temp repo 的测试，默认 contract 必须是 `init_git_test_sandbox` 或 `git_test_sandbox` fixture；
   - 不允许在本 PRD 下再新增并列竞争的第二套 public Python bootstrap path；
   - 如需增强 `tests/conftest.py`，只能做最小、可审计的 contract 内增强。

2. **必须修复当前真实 GitHub CI witness：`tests/test_orchestrator_withdraw.py`**
   - 该文件中的 `repo_env(tmp_path)` 与 `repo_env_main(tmp_path)` 不得继续 hand-roll `git init` / `git commit -m "init"` 作为 bootstrap；
   - 必须迁移到 shared helper；
   - 保留 withdraw 相关断言：baseline alignment、idempotency、governance warning、job teardown、runtime helper usage、main branch alignment、missing metadata fatal path。

3. **必须迁移剩余高风险 Python-side temp-repo bootstrap debt**
   - 下列测试必须审查并迁移其 hand-rolled bootstrap 至 shared helper，除非能被严格证明其现有 git setup 是业务本质而非 bootstrap debt：
     - `tests/test_runtime_role_hook_enforcement.py`
     - `tests/test_cleanup_flag.py`
     - `tests/test_pr_002_orchestrator_lock.py`
     - `tests/test_commit_state.py`
   - “严格证明”不是一句口头说明，而必须体现在测试行为与 contract 的清晰边界上。

4. **必须区分 bootstrap contract 与业务 git 操作**
   - 允许测试在 bootstrap 完成后继续执行其业务场景所需的 `git add` / `git commit` / `git checkout`；
   - 不允许为了“统一”而删除这些业务断言动作；
   - 本 PRD 只消灭 hand-rolled bootstrap，不消灭业务场景中的 git 行为。

5. **必须复核候选 git-dependent Python tests，并明确处理结论**
   - 以下测试必须被 review，判断其 git setup 是否应收敛到 shared helper：
     - `tests/test_doctor_core.py`
     - `tests/test_doctor_hook_schema_version.py`
     - `tests/test_doctor_profiles.py`
     - `tests/test_080_orchestrator_dynamic_strings.py`
   - 对每个文件，结果必须是二选一：
     1. 迁移到 shared helper；或
     2. 明确保留原状，并给出“为什么这是业务本质 git setup 而非 bootstrap debt”的代码级理由。

6. **不得通过 ignore list 制造假绿**
   - 本 PRD 范围内目标不得通过新增 `ignore_tests.json` 条目回避执行；
   - 如果某个测试仍无法完成修复，应显式标记为未完成，而不是 quarantine 掉后宣称完成；
   - 成功必须建立在真实 GitHub-hosted Preflight 的通过或 failure-surface progression 之上。

7. **不得为了迁就测试而修改无关主逻辑 / 恢复已删除 contract**
   - 若某测试依赖历史上已删除的主逻辑 contract，不允许通过恢复旧主逻辑来让测试变绿；
   - 必须优先修正测试，使其对齐当前有效 contract。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 优先修改 `tests/conftest.py` 与目标 pytest files；
   - 不应顺带改动 orchestrator / envelope / core framework 主逻辑，除非存在与 Python bootstrap contract 直接相关、且不可避免的最小 supporting change。

2. **clean-runner parity 必须是设计目标**
   - 所有迁移目标都必须以“fresh HOME / 无 host global git identity”为基本场景设计；
   - 不允许把修复建立在 CI runner 预写 global git config 上。

3. **shared helper contract 必须保持最小、可读、可审计**
   - helper 只负责：初始化 git repo、显式建立 repo-local identity、按调用者要求创建 baseline commit；
   - 不得自动构造与测试业务无关的状态；
   - 不得吞掉 git 错误。

4. **实现必须降低未来 regression 风险**
   - 迁移完成后，新增 Python tests 若需要 commit-capable temp repo，应默认走 shared helper，而不是再次 hand-roll bootstrap。

### User Stories

- **As a maintainer**, I want the remaining Python-side git bootstrap debt removed, so the pytest suite stops passing locally by accident and failing on real GitHub clean runners.
- **As a reviewer**, I want one canonical Python helper for temp-repo bootstrap, so test setup logic stops drifting across multiple pytest files.
- **As an operator**, I want GitHub-hosted `Preflight` to surface real product/test contract problems, not hidden host git identity assumptions inside pytest fixtures.
- **As a future test author**, I want an obvious shared fixture/helper for commit-capable temp repos, so I do not reintroduce the same clean-runner bug class.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **Python-side shared contract convergence** 路线，而不是继续逐个 pytest failure 做 one-off patch。

### 3.1 核心设计决策

1. **`tests/conftest.py` 继续作为唯一 canonical Python-side bootstrap contract**
   - 已有 `init_git_test_sandbox(target_dir, baseline_commit=False)` 与 `git_test_sandbox` fixture；
   - 本 PRD 的核心不是再造 helper，而是让剩余目标真正消费它。

2. **优先修真实 CI witness，再一并收口同类高风险测试**
   - `tests/test_orchestrator_withdraw.py` 是最明确的真实 runner witness，必须优先修；
   - 同类高风险 Python tests 应趁同一波一起收口，避免下一轮继续被 GitHub CI 一项一项打出来。

3. **把“bootstrap debt”与“业务 git 行为”严格区分**
   - 本 PRD 仅替换测试仓库的 commit-capable 初始化步骤；
   - 业务步骤里的 commit / checkout / hook assertions 仍然保留；
   - 不允许把业务 git 行为误删成“统一化”。

4. **候选复核不是可选附录，而是显式范围的一部分**
   - 对剩余 git-dependent Python tests，必须做一次系统 review；
   - 目标不是强行全改，而是明确哪些属于 shared-bootstrap debt，哪些不属于。

### 3.2 推荐实现方向

#### A. Shared helper usage pattern
对于需要 commit-capable temp repo 的 pytest tests，推荐统一模式：
- 使用 `git_test_sandbox(workdir, baseline_commit=True)` 初始化基础仓库；
- 如不需要初始提交，可显式 `baseline_commit=False`；
- 之后由测试自己继续业务场景所需的 `git add` / `git commit` / branch 操作。

#### B. `tests/test_orchestrator_withdraw.py`
- 替换 `repo_env(tmp_path)` 与 `repo_env_main(tmp_path)` 中 hand-rolled bootstrap；
- 复用 shared helper 创建 baseline repo；
- 保持后续针对 withdraw alignment、job teardown、warning、main branch、runtime helper 的业务断言不变。

#### C. High-risk Python-side tests
以下测试默认应按 shared helper 模式迁移，除非审查后能证明其现有 git setup 是业务本质：
- `tests/test_runtime_role_hook_enforcement.py`
- `tests/test_cleanup_flag.py`
- `tests/test_pr_002_orchestrator_lock.py`
- `tests/test_commit_state.py`

#### D. Review-only candidates
以下测试必须 review，并形成显式处理结论：
- `tests/test_doctor_core.py`
- `tests/test_doctor_hook_schema_version.py`
- `tests/test_doctor_profiles.py`
- `tests/test_080_orchestrator_dynamic_strings.py`

### 3.3 明确不采用的方案

1. **不通过 GitHub Actions 预写 global git config 修复**
   - 这会掩盖 repo 内 contract 问题，而不是解决它。

2. **不新增第二套 Python public helper**
   - 这会把刚建立的 shared contract 再次分叉。

3. **不通过 ignore list 让范围内目标退出执行面**
   - 这会制造假绿，违背本 PRD 目标。

4. **不为过时测试恢复已删除主逻辑 contract**
   - 如果测试依赖旧 contract，应修测试，不修产品主逻辑。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: `tests/test_orchestrator_withdraw.py` no longer fails during temp-repo bootstrap on a clean runner**
  - **Given** a clean-runner-like environment with no host global git identity
  - **When** `pytest tests/test_orchestrator_withdraw.py` is executed
  - **Then** the test completes without failing at temporary repo bootstrap `git commit -m "init"`
  - **And** all original withdraw-related assertions in that test continue to pass

- **Scenario 2: High-risk Python-side temp-repo tests remain behaviorally meaningful after migration**
  - **Given** the high-risk Python-side tests covered by this PRD
  - **When** they are executed in a clean-runner-like environment after migration
  - **Then** they pass without host-global git identity assumptions in their bootstrap path
  - **And** they still validate their original hook / lock / cleanup / commit-state behaviors rather than merely avoiding setup failure

- **Scenario 3: Candidate git-dependent Python tests either run cleanly under the shared contract or are explicitly left outside this failure class**
  - **Given** the candidate git-dependent Python tests reviewed under this PRD
  - **When** they are executed in a clean-runner-like environment
  - **Then** any test that depends on commit-capable temporary repo bootstrap runs successfully without host-global git identity
  - **And** any remaining failure, if present, must come from a different product or test-contract failure class rather than the bootstrap class addressed here

- **Scenario 4: No fake green via ignore-list quarantine**
  - **Given** the files covered by this PRD
  - **When** implementation and verification complete
  - **Then** the tests are still exercised on the real preflight surface rather than being hidden behind newly added ignore-list entries
  - **And** completion is evidenced by actual execution outcomes instead of quarantine

- **Scenario 5: Real GitHub-hosted Preflight progresses past the current Python-side git-bootstrap witness failure**
  - **Given** the implementation has landed on the target branch
  - **When** a subsequent real GitHub-hosted `Preflight` run executes
  - **Then** the current Python-side git bootstrap witness failure no longer appears in the failure summary
  - **And** any remaining pytest failures, if present, must come from unrelated failure classes rather than this bootstrap class

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本 PRD 的核心风险不是“helper 写错”，而是：

1. 只修单个 witness，而把同类高风险 Python bootstrap debt 留在 repo 中，导致下一轮 CI 再次暴露同类 failure；
2. 为了统一 helper，误删了测试原本的业务 git 行为断言；
3. 通过 ignore / skip / weakening assertions 制造表面 green；
4. 把问题修成“本地 pass”，却没有用真实 GitHub-hosted runner 验证 clean-runner parity。

### Verification Strategy

#### A. Structural convergence verification
需要验证：
- `tests/test_orchestrator_withdraw.py` 与高风险目标不再 hand-roll bootstrap；
- `tests/conftest.py` 仍然是唯一 canonical Python-side helper contract；
- 范围内文件不再复制分叉 helper 逻辑。

#### B. Helper contract verification
需要验证：
- `init_git_test_sandbox` 在 fresh `HOME` / 无 host global git identity 下仍能成功初始化 commit-capable repo；
- `baseline_commit=True` 行为保持显式、最小、可预测；
- helper 不自动生成与测试业务无关的状态。

#### C. Test-intent preservation verification
需要验证：
- 迁移后每个测试仍验证原来的 withdraw / hook / lock / commit-state / cleanup 语义；
- 不是因为删断言、吞错误或 skip 路径而“过”。

#### D. Candidate review / scope-resolution verification
需要验证：
- 高风险目标已真正迁移到 shared helper；
- review-only 候选文件都得到显式处理结论：迁移，或以清晰理由保留原状；
- 这类处理结论记录在实现与 review 结果中，而不是模糊遗留。

#### E. Real clean-runner verification
需要覆盖：
- 本地近似 clean-runner 环境验证；
- 真实 GitHub-hosted `Preflight` 验证；
- 重点关注 `tests/test_orchestrator_withdraw.py` witness 是否从 failure surface 消失。

### Quality Goal
本 PRD 的质量目标不是“再修一支 pytest”，而是：

> **把 repo 中剩余的 Python-side temp-repo bootstrap debt 收敛到 shared helper contract，让 pytest 面这类 clean-runner git identity/bootstrap failure 不再继续反复出现，并把 GitHub-hosted Preflight 的信号重新拉回到真实产品/contract failure。**

## 6. Framework Modifications (框架防篡改声明)
- `tests/conftest.py`
- `tests/test_orchestrator_withdraw.py`
- `tests/test_runtime_role_hook_enforcement.py`
- `tests/test_cleanup_flag.py`
- `tests/test_pr_002_orchestrator_lock.py`
- `tests/test_commit_state.py`
- `tests/test_doctor_core.py`（仅在审查后确认需要迁移 bootstrap 时）
- `tests/test_doctor_hook_schema_version.py`（仅在审查后确认需要迁移 bootstrap 时）
- `tests/test_doctor_profiles.py`（仅在审查后确认需要迁移 bootstrap 时）
- `tests/test_080_orchestrator_dynamic_strings.py`（仅在审查后确认需要迁移 bootstrap 时）
- `ignore_tests.json`（仅允许检查与验证，不授权新增 quarantine 作为完成手段）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 第一波 / 第二波优先解决 bash、mocked E2E 与最暴露的 clean-runner witness paths，并建立 Python-side helper contract。
- **Observed correction**: 虽然 `tests/conftest.py` 已引入 helper，真实 GitHub-hosted Preflight 仍证明部分 Python-side tests 没有实际迁入 unified contract，导致 `tests/test_orchestrator_withdraw.py` 暴露同类 failure。
- **v2.0 Revision Rationale**: 将剩余 Python-side git bootstrap debt 从 umbrella pytest issue 中切为具体 child slice，集中收口 helper 消费面，并明确高风险目标与 review-only 候选的处理边界。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
```text
None
```
