---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Second-Wave Git Test Bootstrap Debt Consolidation

## 1. Context & Problem (业务背景与核心痛点)
第一波 PRD `PRD_Unify_Git_Test_Sandbox_Initialization_for_Clean_Runner_Parity.md` 已经完成了它原本授权的 first-wave 目标：
- 在 `scripts/e2e/setup_sandbox.sh` 中建立了 canonical git test sandbox bootstrap contract；
- 将首批高价值 bash / mocked E2E tests 迁移到统一 helper；
- 且这些首批目标当前不在 `ignore_tests.json` 中，并非通过 quarantine 假绿。

但是，后续真实 GitHub-hosted `Preflight` 与本地静态扫描都表明：仓库内仍存在第二批可见的同类测试债务。

核心问题没有变：

> **仍有一批测试在临时 sandbox git repo 中执行 `git init` / `git commit` 时，手工依赖散点 bootstrap、inline repo-local identity setup，或等价的 ad hoc commit bootstrap，而不是统一 contract。**

这意味着：
- clean-runner parity 仍然没有扩展到整个当前可见测试面；
- CI 上继续可能出现“本地绿、GitHub clean runner 红”的伪差异；
- 第一波 helper 的价值会被剩余散点实现持续稀释；
- 如果继续只按当前最先爆出的单个失败项逐个补丁，会继续形成长期打地鼠。

当前扫描可见的 second-wave 候选集包括：

### Top-level bash tests
- `scripts/test_missing_channel.sh`
- `scripts/test_create_pr_contract.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`
- `scripts/test_deploy_hardcopy.sh`（仅当其 `git init` 用法经确认属于临时测试 sandbox bootstrap debt 时纳入）

### Mocked E2E tests
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/e2e/mocked/e2e_test_forensic_quarantine.sh`
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh`
- `scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh`
- `scripts/e2e/mocked/e2e_test_anti_reward_hacking.sh`
- `scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh`
- `scripts/e2e/mocked/e2e_test_ignition_guardrail.sh`
- `scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh`

### Tests / pytest-side repo bootstrap paths
- `tests/test_069_git_namespace_and_teardown.sh`
- `tests/test_071_reviewer_history_scope.sh`
- `tests/test_075_safe_git_checkout.sh`
- `tests/test_playbook_injection.sh`
- `tests/test_065_path_hijack.sh`
- `tests/test_076_unit_git_commit.sh`
- `tests/test_1012_reviewer_guardrail_deadlock.sh`
- `tests/test_git_hook.sh`
- `tests/test_orchestrator_doctor.py`

本 PRD 的目标不是重构所有 Git 相关测试逻辑，也不是重写所有业务断言，而是：

> **把当前扫描可见、与临时测试 repo 初始化 / git identity / baseline commit bootstrap 直接相关的剩余债务统一收口到 canonical contract（或其 Python 等价 wrapper），从而把 clean-runner parity 从 first-wave 扩展到当前可见的第二波测试面。**

本 PRD 不覆盖：
- 与 git bootstrap / git identity 无关的 pytest 失败根因；
- 所有 Git 业务逻辑测试的全面重构；
- 通过新增 ignore list 条目、弱化断言、吞错误或跳过测试来制造表面 green；
- 与 test harness bootstrap debt 无关的 orchestrator 主逻辑重构。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **第二波剩余 bash / mocked E2E temp-repo bootstrap debt 必须迁移到 canonical shared path**
   - 对于 Bash / mocked E2E 场景，`scripts/e2e/setup_sandbox.sh` 必须继续作为唯一 canonical shared entrypoint；
   - 不允许在第二波中新增与其平行竞争的第二公共 bash bootstrap 入口；
   - 已扫描到的剩余 bash / mocked E2E 目标中，与临时测试 repo commit 能力直接相关的 bootstrap 逻辑必须迁移到该 canonical path。

2. **必须为 Python / pytest repo bootstrap 场景提供等价统一 contract**
   - 第二波不允许继续把 Python 测试永久排除在统一 contract 之外；
   - 对 Python / pytest 中会自建临时 git repo 并执行 commit 的测试，必须提供共享、显式、可复用的 bootstrap wrapper / fixture contract；
   - 该 Python-side contract 可以复用现有 canonical 逻辑、调用 supporting helper，或通过等价 hermetic repo-local setup 实现，但对调用者必须保持统一、可审计、非散点的接口。

3. **统一 contract 必须继续保证 clean-runner-safe 的最小 commit 能力**
   - 无论 Bash / mocked E2E 还是 Python / pytest 侧，临时 repo 的最小 commit 能力都必须显式建立在 repo-local identity 或等价 hermetic 机制上；
   - 不得依赖宿主机 global git config；
   - 目标仍然是在 fresh `HOME` / 无 global git config 环境下可以完成最小 commit。

4. **第二波迁移必须只替换 bootstrap debt，不得改写原始业务断言目标**
   - 每个迁移测试仍必须验证其原本 intended product / contract / guardrail / mocked-state path；
   - 不允许把“测试不再在 `git commit` 阶段挂掉”误当作完成标准；
   - 不允许通过删断言、放宽行为校验、吞掉失败来伪修复。

5. **第二波迁移目标中的散点 inline repo-local identity/bootstrap 逻辑必须删除或收敛**
   - 第二波文件中，不得在迁移后继续保留并行的 `git init` + `git config --local user.name/user.email` bootstrap 实现作为“备用方案”；
   - 允许测试保留其业务上需要的后续 `git add` / `git commit` 动作；
   - 但“让 repo 具备 commit 能力”的初始化 contract 必须统一收口。

6. **不得依赖 ignore list 制造假绿**
   - 对本 PRD 明确纳入的第二波目标，不得通过新增 `ignore_tests.json` 条目回避执行；
   - 如果当前实现需要暂时 quarantine，必须明确标记为未完成而不是宣称已修复；
   - 本 PRD 的成功标准必须建立在测试真实执行并通过之上，而不是被 ignore。

7. **第二波交付后，新增同类测试必须默认走统一 contract**
   - Bash / mocked E2E 场景默认走 `scripts/e2e/setup_sandbox.sh` canonical path；
   - Python / pytest 场景默认走本 PRD 新增或固化的 shared wrapper / fixture contract；
   - 避免未来继续回到散点 hand-rolled bootstrap。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 优先修改测试基础设施、测试脚本与测试辅助文件；
   - 除非某个 supporting helper 必须最小调整，否则不应顺带重构与本问题无关的 orchestrator 主逻辑。

2. **clean-runner parity 必须从 first-wave 扩展到当前可见 second-wave 测试面**
   - 设计目标不是“修某一支脚本碰巧不炸”；
   - 而是让当前可见第二波目标在本地近 clean-runner 与真实 GitHub-hosted runner 上拥有一致 bootstrap contract。

3. **Python-side contract 必须保持可读、可复用、可审计**
   - 不允许把 Python 测试改成各自复制一段 `subprocess.run(["git", "config", ...])` 的分散实现；
   - 应形成一条清晰的默认复用路径。

4. **不得通过 CI 宿主机预配置修复**
   - 不允许在 GitHub Actions workflow 中新增 global git config 作为主方案；
   - 问题必须在 repo 内测试 contract 层解决。

5. **不得把“所有 Git 相关测试逻辑重构”作为第二波目标膨胀**
   - 本 PRD 只处理临时测试 repo bootstrap debt；
   - 不处理与 bootstrap 无关的 Git 业务语义重写。

### User Stories

- **As a maintainer**, I want the remaining visible temp-repo bootstrap debt cleaned up in one coordinated second wave, so GitHub clean-runner failures stop rediscovering the same hidden assumption one file at a time.
- **As a reviewer**, I want bash, mocked E2E, and python tests to share an auditable bootstrap contract instead of scattered inline `git init` / `git config` snippets, so future drift is easier to detect.
- **As an operator**, I want real GitHub-hosted Preflight results to reflect product and contract regressions, not missing git identity setup in leftover test harnesses.
- **As a future test author**, I want a clear default path for creating commit-capable temporary repos regardless of language, so I do not have to rediscover clean-runner gotchas.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **second-wave consolidation of visible bootstrap debt** 路线，而不是继续按“当前最先 fail 的单个测试”打地鼠。

### 3.1 核心设计决策

1. **继续坚持单一 canonical bash entrypoint**
   - 对 Bash / mocked E2E，`scripts/e2e/setup_sandbox.sh` 仍必须保持唯一 public canonical entrypoint；
   - 第二波不授权引入第二个并列公共 bash bootstrap 入口。

2. **将 second-wave 范围定义为“当前扫描可见的 bootstrap debt”，而非“所有 Git 测试全面重构”**
   - 这样可以最大化清理同类 debt，又避免 PRD 范围膨胀成无边界的大重构；
   - 重点是清掉 `git init` / inline identity / baseline bootstrap 的散点实现，而不是重写每个测试的业务剧本。

3. **补上 Python / pytest 侧统一 contract，而不是永远只修 Bash**
   - 第一波有意允许 Python 暂时不统一；
   - 第二波必须把这个缺口补上，否则 clean-runner debt 仍会在 pytest suite 中持续存在。

4. **允许最小 supporting helper，但不允许 contract 漂移**
   - 如果 Python 侧需要新增 helper / fixture / wrapper，这可以接受；
   - 但其职责必须与 bash canonical contract 一致：仅负责 commit-capable sandbox bootstrap，不自动构造业务状态，不吞失败，不注入无关副作用。

5. **明确拒绝 ignore-list 驱动的表面完成**
   - 第二波必须把“禁止靠 ignore list 假绿”写入成功定义；
   - 否则 UAT / preflight 通过可能只是 quarantine debt，而不是 structural fix。

### 3.2 推荐实现方向

#### A. Bash / mocked E2E 路径
- 继续以 `scripts/e2e/setup_sandbox.sh` 为唯一 canonical public entrypoint；
- 将 second-wave 剩余 top-level bash tests 与 mocked E2E tests 中与 temp-repo bootstrap directly related 的逻辑迁移到 `init_git_test_sandbox` 或其在该文件中的最小扩展；
- 删除这些文件中重复的 `git init` / repo-local identity bootstrap 片段。

#### B. Python / pytest 路径
- 引入一个共享、可审计的 Python-side bootstrap contract；
- 可以是：
  1. 直接复用 bash canonical helper；
  2. 新增最小 Python helper / fixture；
  3. 或新增 supporting helper 被 bash / python 共同复用；
- 但外部 contract 必须保持一致：
  - 初始化目标 repo；
  - 建立 repo-local commit capability；
  - baseline commit 必须显式可控；
  - 不构造业务状态；
  - 不掩盖 git 错误。

#### C. Scope confirmation rule for ambiguous files
- `scripts/test_deploy_hardcopy.sh` 这类包含 `git init` 但是否属于 temp sandbox bootstrap debt 尚不完全明确的文件，必须先确认其 `git init` 使用目的；
- 若其 `git init` 仅用于测试 sandbox bootstrap，则纳入统一 contract；
- 若其 `git init` 属于与当前 PRD 无关的业务语义，则不得为追求“大而全”强行改写。

### 3.3 第二波迁移目标

#### 必须覆盖的目标
- `scripts/test_missing_channel.sh`
- `scripts/test_create_pr_contract.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/e2e/mocked/e2e_test_forensic_quarantine.sh`
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh`
- `scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh`
- `scripts/e2e/mocked/e2e_test_anti_reward_hacking.sh`
- `scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh`
- `scripts/e2e/mocked/e2e_test_ignition_guardrail.sh`
- `scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh`
- `tests/test_069_git_namespace_and_teardown.sh`
- `tests/test_071_reviewer_history_scope.sh`
- `tests/test_075_safe_git_checkout.sh`
- `tests/test_playbook_injection.sh`
- `tests/test_065_path_hijack.sh`
- `tests/test_076_unit_git_commit.sh`
- `tests/test_1012_reviewer_guardrail_deadlock.sh`
- `tests/test_git_hook.sh`
- `tests/test_orchestrator_doctor.py`

#### 条件纳入目标
- `scripts/test_deploy_hardcopy.sh`（仅当确认其 `git init -q` 属于 temp sandbox bootstrap debt）

如实现中发现某个 shared helper、fixture、或 common support file 必须一并调整，可做最小 supporting change。

### 3.4 明确不采用的方案

1. **不采用继续逐个测试 one-off 补 `git config --local` 的长期方案**
   - 这会继续制造散点 drift，不是 structural fix。

2. **不采用 GitHub Actions 层 global git config 预配置**
   - 这会掩盖 repo 内 contract 问题，而非解决它。

3. **不采用通过新增 ignore_tests.json 条目让目标测试退出执行面**
   - 这会制造假绿，违背本 PRD 目标。

4. **不采用“大扫除式”重写所有 Git 业务测试逻辑**
   - 这会让 blast radius 膨胀，偏离当前问题核心。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Second-wave bash targets use the canonical sandbox bootstrap instead of scattered inline setup**
  - **Given** a second-wave bash test that creates a temporary git repo and needs commit capability
  - **When** the test is migrated under this PRD
  - **Then** it obtains that capability through the canonical shared sandbox bootstrap path
  - **And** it no longer relies on parallel inline repo-local identity bootstrap snippets

- **Scenario 2: Second-wave mocked E2E targets become clean-runner-safe without weakening their orchestration assertions**
  - **Given** a second-wave mocked E2E test that creates temporary repos and performs setup commits
  - **When** it is executed in a clean-runner-like environment with no host global git identity
  - **Then** the required setup commits succeed through the shared contract
  - **And** any failure that remains must arise only from its intended mocked orchestration / resilience / state-machine assertions

- **Scenario 3: Python / pytest-side repo bootstrap becomes explicit and shared**
  - **Given** a Python / pytest test that creates a temporary git repo and needs to commit inside it
  - **When** the test is migrated under this PRD
  - **Then** it uses a shared, explicit python-side bootstrap contract instead of hand-rolled scattered setup
  - **And** the repo can perform the minimal required commit without host global git config

- **Scenario 4: Second-wave migrated tests still reach their original intended assertion paths**
  - **Given** the second-wave migrated bash, mocked E2E, and python-side targets
  - **When** they run after migration
  - **Then** they still validate their original product / contract / guardrail / orchestration behaviors
  - **And** they do not merely pass because bootstrap failures were masked or assertions were weakened

- **Scenario 5: No fake green via new ignore-list quarantine for second-wave targets**
  - **Given** the target files explicitly covered by this PRD
  - **When** preflight and local validation are executed after implementation
  - **Then** those targets remain in the real execution surface rather than being newly added to `ignore_tests.json`
  - **And** any claim of completion must be backed by actual execution rather than quarantine

- **Scenario 6: Real GitHub-hosted Preflight no longer fails on the second-wave bootstrap debt class**
  - **Given** the second-wave consolidation has landed on the target branch
  - **When** a subsequent real GitHub-hosted `Preflight` run executes on that branch
  - **Then** the previously affected second-wave tests no longer fail due to missing git identity / temp-repo bootstrap debt
  - **And** any remaining failure, if present, must come from unrelated assertion surfaces rather than the bootstrap class addressed here

- **Scenario 7: Issue #29 witness path is progressed past on a real GitHub runner**
  - **Given** this second-wave work is complete and merged
  - **When** a subsequent real GitHub-hosted `Preflight` run executes on the target branch
  - **Then** `scripts/test_pr_003.sh` no longer appears as a failure item caused by sandbox git bootstrap debt
  - **And** this issue can only be considered for closure after that real GitHub evidence exists

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
第二波最大的风险不是“再漏掉 1-2 个脚本”，而是：

1. 仓库继续同时存在 canonical contract 与散点 hand-rolled bootstrap，两套规则并存；
2. Python / pytest 侧仍未纳入统一 contract，导致 CI 上反复暴露 clean-runner git commit 问题；
3. 为追求快速 green，目标测试被悄悄加入 ignore list，形成 debt-quarantine 假绿；
4. 修复过程中误改测试原始业务断言，导致“看起来更稳”但实际上 coverage 变弱。

### Verification Strategy

#### A. Structural convergence verification
需要验证：
- second-wave 目标中的 bootstrap debt 已收敛到 canonical path 或 python-side shared wrapper；
- 第二波文件中不再保留并行 inline repo-local identity bootstrap；
- 没有新增与 canonical bash path 平行竞争的第二 public bash entrypoint。

#### B. Helper / wrapper contract verification
需要验证：
- Bash canonical helper 与 Python-side wrapper 在 fresh `HOME` / 无 global git config 环境下都能建立可提交 repo；
- baseline commit 仍保持显式、最小、幂等或 fail-closed；
- contract 仍不自动生成业务状态、不吞 git 错误、不偷偷补业务文件。

#### C. Second-wave migration verification
需要验证：
- 每个纳入目标都已迁移到统一 contract；
- 不再因缺失 git identity / bootstrap 在 repo setup 阶段失败；
- 仍进入原本 intended assertion path，而不是通过弱化行为校验“过关”。

#### D. Anti-fake-green verification
需要验证：
- 本 PRD 目标未被新增到 `ignore_tests.json`；
- `preflight.sh --report-all` 的结果中，若目标相关问题消失，必须是因为真实执行通过而不是被 quarantine；
- 若仓库整体仍有 ignore debt，需要在验收说明中明确区分“本 PRD 目标真实执行通过”与“全仓 true full green”。

#### E. Real clean-runner verification
需要覆盖：
- 本地近似 clean-runner 环境（`env -i` + fresh `HOME`）执行；
- 后续真实 GitHub-hosted `Preflight` run 观察 second-wave failure surface 是否被推进；
- 特别需要验证 `scripts/test_pr_003.sh` 已不再作为 clean-runner bootstrap debt witness 失败项出现，才能支持 #29 关闭。

### Quality Goal
本 PRD 的质量目标不是“再多修几个脚本”，而是：

> **把当前扫描可见的 git test bootstrap debt 进行第二波系统性收口，让 Bash、mocked E2E、与 Python / pytest 场景都拥有统一、clean-runner-safe、非散点的 commit-capable sandbox contract，并确保真实 GitHub-hosted Preflight 不再因为这类 bootstrap debt 继续报错。**

## 6. Framework Modifications (框架防篡改声明)
- `scripts/e2e/setup_sandbox.sh`
- Python-side shared bootstrap helper / fixture files required to establish the unified contract
- `preflight.sh`（仅在需要最小增强验收可见性、且不改变 truthful semantics 的前提下）
- `ignore_tests.json`（仅允许检查与验证，不授权通过新增目标 ignore 来制造表面 green）
- `scripts/test_missing_channel.sh`
- `scripts/test_create_pr_contract.sh`
- `scripts/test_missing_force_replan.sh`
- `scripts/test_orchestrator_logs.sh`
- `scripts/test_deploy_hardcopy.sh`（仅当 scope confirmation 成立）
- `scripts/e2e/mocked/e2e_test_preflight_guardrails.sh`
- `scripts/e2e/mocked/e2e_test_forensic_quarantine.sh`
- `scripts/e2e/mocked/e2e_test_secure_prompt.sh`
- `scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh`
- `scripts/e2e/mocked/e2e_test_anti_reward_hacking.sh`
- `scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh`
- `scripts/e2e/mocked/e2e_test_ignition_guardrail.sh`
- `scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh`
- `tests/test_069_git_namespace_and_teardown.sh`
- `tests/test_071_reviewer_history_scope.sh`
- `tests/test_075_safe_git_checkout.sh`
- `tests/test_playbook_injection.sh`
- `tests/test_065_path_hijack.sh`
- `tests/test_076_unit_git_commit.sh`
- `tests/test_1012_reviewer_guardrail_deadlock.sh`
- `tests/test_git_hook.sh`
- `tests/test_orchestrator_doctor.py`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 第一波先处理 `scripts/test_pr_003.sh` 及相邻 preflight-facing 高价值 bash / mocked E2E witness tests，建立 canonical helper 并验证 shared contract 可行。
- **Observed correction**: 第一波完成后，真实 GitHub-hosted Preflight 与本地静态扫描都显示，仓库其余 bash / mocked E2E / python-side temp-repo bootstrap debt 仍然存在；若继续只修当前最先爆出的个别 failure item，会继续陷入打地鼠。
- **v2.0 Revision Rationale**: 将范围升级为 second-wave visible debt consolidation：系统性收口当前扫描可见的剩余 bootstrap debt，并补上 Python / pytest-side unified contract，同时明确禁止通过 ignore list 制造表面 green。

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
