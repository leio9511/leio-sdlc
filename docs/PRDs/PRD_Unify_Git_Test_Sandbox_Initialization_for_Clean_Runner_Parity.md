---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Unify Git Test Sandbox Initialization for Clean Runner Parity

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 的 Preflight stabilization EPIC (#8) 进入 true-green recovery 阶段后，真实 GitHub-hosted clean runner 开始持续暴露一类此前被作者本地环境掩盖的问题：

> **测试脚本/测试用例在临时 sandbox git repo 中执行 `git commit` 时，隐式依赖了宿主机已经存在的 global git identity，而没有自带最小 repo-local bootstrap contract。**

这个问题已经不再是推测。

在 #25 / #30 对应的 orchestrator bash tests 中，我们已经确认并修复了该类 clean-runner gap；随后在 #29 中，`scripts/test_pr_003.sh` 又在真实 GitHub clean runner 上失败。进一步在近似 clean-runner 的本地环境（`env -i` + fresh temporary `HOME`）中复现可见：该脚本在真正进入其 intended orchestrator assertion path 之前，就先在 `git commit -m "init"` 处因缺失 git identity 而失败。

这说明：
- 当前问题不是单一脚本的偶发回归；
- 而是一类 **test-harness-level design debt**；
- 只继续逐个脚本补 `git config --local` 会形成长期打地鼠；
- repo 需要一个共享、明确、可复用的 **git test sandbox initialization contract**。

本 PRD 的目标不是修改 orchestrator 产品逻辑，而是：

> **为所有“会在临时测试 repo 中执行 commit”的测试建立统一 helper / 统一初始化契约，使其在没有任何宿主机 global git config 的 clean runner 上仍能自给自足地完成最小 repo bootstrap，并稳定进入各自真正要验证的业务/契约路径。**

本 PRD 重点是首批高价值 / preflight-facing 测试的统一 hardening，不要求一次性治理全仓所有测试。

本 PRD 不覆盖：
- 与 git identity 无关的 pytest 失败根因；
- 与 mocked E2E 业务状态机本身相关的产品逻辑问题；
- 将所有测试基础设施重构为大而全的新框架；
- 通过削弱断言、吞错误或跳过测试来换取表面 CI 变绿。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须引入共享的 git test sandbox initialization helper / contract**
   - 该 contract 必须服务于“测试创建临时 git repo 并需要执行 commit”的场景；
   - 不允许继续把 repo-local identity setup 作为脚本作者手工重复实现的隐性约定；
   - 对于 Bash / mocked E2E 测试，这个 contract 必须收敛到仓库现有的公共 sandbox fixture `scripts/e2e/setup_sandbox.sh`，或在不改变其唯一 canonical 入口地位的前提下做最小扩展。

2. **helper 必须保证 clean-runner-safe 的最小 commit 能力**
   - helper 必须显式建立 repo-local git identity，或采用等价且 hermetic 的方式保证 `git commit` 不依赖宿主机 global git config；
   - helper 的行为目标是让测试在 fresh HOME / 无 global git config 环境下仍可执行最小 commit。

3. **helper 职责必须保持最小且可预期**
   - helper 只负责“测试 git sandbox 可提交初始化契约”；
   - 不负责替测试自动构造具体业务状态；
   - 不得偷偷吞掉 git 错误或弱化失败语义；
   - 不得自动创建 PRD / job / mocked state；
   - 不得自动运行 `doctor.py --fix`、自动清理工作区、或自动写入与调用场景无关的测试业务文件；
   - 如支持 baseline commit，也只能提供显式、最小、调用者可控的 commit 能力，不得擅自制造额外业务状态。

4. **首批高价值测试必须迁移到统一 helper**
   - 首批迁移范围至少包括：
     1. `scripts/test_pr_003.sh`
     2. `scripts/test_polyrepo_context.sh`
     3. `scripts/test_cwd_guardrail.sh`
     4. `scripts/test_escalation_clean.sh`
     5. `scripts/test_pre_commit_hook.sh`
     6. `scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh`
     7. `scripts/e2e/mocked/e2e_test_uat_orchestrator.sh`
     8. `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`
   - 其中：
     - `scripts/test_pr_003.sh` 是已在 near-clean-runner 环境中复现确认的实锤案例；
     - 其余首批文件是基于静态扫描和 preflight-facing 价值判断选出的同类高风险迁移对象。

5. **首批迁移文件中，与 git identity/bootstrap directly related 的重复内联逻辑必须删除或收敛**
   - 不允许在引入 shared contract 之后，首批迁移文件仍继续保留各自平行、重复、易漂移的 repo-local identity bootstrap 实现；
   - 对于 Bash / mocked E2E 路径，相关能力必须收敛到 `scripts/e2e/setup_sandbox.sh` 这一 canonical 公共入口，或其最小必要扩展；
   - 目标是形成一个清晰、可审计的统一 contract，而不是新增 helper 同时保留旧散点实现。

6. **迁移后测试必须仍然进入原本 intended assertion path**
   - 例如：
     - `test_pr_003.sh` 仍然要验证 JIT prompt / default engine contract；
     - `test_pre_commit_hook.sh` 仍然要验证 hook / guardrail contract；
     - mocked E2E tests 仍然要验证各自原始状态机 / resilience / UAT path。
   - 不允许把“测试不再在 git commit 阶段挂掉”误当作完成标准。

7. **新 helper 必须成为后续新增同类测试的默认做法**
   - PRD 交付后的 repo 内部应形成清晰约定：凡是新测试需要在临时 repo commit，必须走统一 helper 或等价统一入口；
   - 避免同类问题在未来继续重复生成。

### Non-Functional Requirements

1. **clean-runner parity 必须是设计目标，不是附带结果**
   - helper 和首批迁移测试必须显式以“无宿主机 global git config”为基本场景设计。

2. **blast radius 必须受控**
   - 优先修改测试基础设施和测试脚本；
   - 不应顺带重构与本问题无关的 orchestrator 主逻辑。

3. **实现应兼容 Bash 与 Python 场景的演进**
   - 首批可以先以 Bash helper 为主，但设计上不能把 Python 测试永久排除在外；
   - 如果需要 wrapper，也应保持 contract 一致。

4. **不得通过依赖 CI 宿主机预配置来修复**
   - 不允许把修复方案建立在“给 GitHub Actions runner 预先写 global git config”之上；
   - 问题应在测试自身 / repo 内 contract 层解决。

### User Stories

- **As a maintainer**, I want tests that create temporary git repos to be self-contained, so a local pass and a clean GitHub runner pass mean the same thing.
- **As a reviewer**, I want one shared git sandbox initialization contract instead of repeated hand-written repo bootstrap snippets, so the repo stops accumulating hidden environment assumptions.
- **As an operator**, I want Preflight failures to reflect real product or contract regressions, not accidental missing git identity in test harness setup.
- **As a future test author**, I want a standard helper to initialize commit-capable temporary repos, so I do not have to remember undocumented clean-runner gotchas.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **shared test bootstrap contract** 路线，而不是继续“逐个脚本散落补丁”。

### 3.1 核心设计决策

1. **从单点修补升级为统一 helper**
   - 这类问题已经跨多个 bash test / mocked E2E test 重复出现；
   - 继续 one-off patch 会导致未来新增测试再次漏配；
   - 因此应把“临时 repo 可提交初始化”抽象为共享 helper。

2. **repo-local identity 优先，禁止依赖 host global identity**
   - helper 必须在 repo 内显式设置最小 identity；
   - 不允许把 `git commit` 能否成功建立在作者机器或 CI runner 的 global 配置上。

3. **helper 职责保持最小，不做业务场景魔法**
   - helper 只解决：初始化 git repo / 建立 repo-local commit contract / 可选最小 baseline commit；
   - helper 不替测试构建业务特定文件、PRD 内容、状态机数据或断言逻辑。

4. **首批迁移先覆盖 Preflight 高价值路径**
   - 不追求一次性 sweeping rewrite 全仓所有测试；
   - 先覆盖当前最能影响真实 clean-runner preflight 信号的脚本。

### 3.2 推荐实现方向

本 PRD 不授权新增一套与现有 sandbox fixture 平行竞争的第二 bootstrap abstraction。

对于 Bash / mocked E2E tests，**`scripts/e2e/setup_sandbox.sh` 必须被视为唯一 canonical shared entrypoint**。新的 git test sandbox bootstrap contract 必须通过以下两种方式之一落地：

1. 直接扩展 `scripts/e2e/setup_sandbox.sh`，让其承担 clean-runner-safe 的最小 git commit bootstrap 能力；或
2. 在其内部调用一个最小 supporting helper，但对测试调用者暴露的公共入口仍然必须保持为 `scripts/e2e/setup_sandbox.sh`，不得让仓库演化出第二个并列公共入口。

实现必须满足以下要求：

1. 可在调用方提供的目标 sandbox 目录上工作；目标目录可以预先存在，也可以由该 contract 在最小必要范围内创建；
2. 可在指定目录初始化测试 git repo；
3. 显式配置 repo-local `user.name` / `user.email`（或等价 hermetic commit env）；
4. baseline commit 必须是调用方显式可控的行为：如支持创建最小 baseline commit，必须由调用方明确请求，不能默认擅自创建额外业务状态；
5. 在调用者侧保持简单、可复用、可读；
6. 重复调用必须保持幂等或至少 fail-closed：不得因为重复初始化而制造未请求的额外业务文件、额外业务 commit、或隐藏状态漂移；
7. 不得自动运行 `doctor.py --fix`、自动创建 PRD/job/mocked state、或自动注入与 sandbox bootstrap 无关的测试业务数据；
8. 允许 Bash 测试直接调用；
9. 首批不要求同步统一改造 Python tests，但该 contract 的设计不得把未来 Python wrapper 或等价复用路径锁死在另一套规则之外。

### 3.3 首批迁移范围与筛选原则

首批纳入不是随意点名，而应遵循以下筛选原则：

1. 已直接出现在当前真实 GitHub Preflight failure surface，或属于紧邻该 surface 的高价值 preflight-facing test；
2. 测试会自建临时 git repo 并执行 commit；
3. 当前未通过统一 helper 建立 clean-runner-safe 的 commit contract；
4. 优先选择最能减少继续打地鼠风险的 contract / mocked E2E tests。

基于上述原则，本 PRD 首批授权迁移以下文件到统一 helper：

- `scripts/test_pr_003.sh`
- `scripts/test_polyrepo_context.sh`
- `scripts/test_cwd_guardrail.sh`
- `scripts/test_escalation_clean.sh`
- `scripts/test_pre_commit_hook.sh`
- `scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh`
- `scripts/e2e/mocked/e2e_test_uat_orchestrator.sh`
- `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`

如实现中发现某个直接 supporting helper / common script 必须一并调整，可做最小 supporting change。

### 3.4 明确不采用的方案

1. **不采用 GitHub Actions 层预写 global git config 作为修复主方案**
   - 这会掩盖 repo 内部测试 contract 问题；
   - 也会继续造成“本地/CI 等价性”不清晰。

2. **不采用与 `scripts/e2e/setup_sandbox.sh` 平行竞争的第二公共 bootstrap 入口**
   - 这会把当前问题从“散点 bootstrap 漏洞”升级成“散点抽象漂移”；
   - 对 Bash / mocked E2E tests，公共入口必须保持单一。

3. **不采用每个测试各自重复内联 git identity setup 的散点修法作为长期方案**
   - 这最多是临时止血，不是结构性修复。

4. **不采用弱化测试断言来换取 green**
   - 目标是让测试进入 intended product/contract path 后再断言，而不是把测试变成空壳。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Shared helper creates a commit-capable temporary git repo without host global identity**
  - **Given** a fresh environment with no preconfigured global git identity
  - **When** a test initializes its temporary git sandbox through the shared helper
  - **Then** the repo can perform the minimal required `git commit`
  - **And** the success does not rely on host/global git config

- **Scenario 2: `scripts/test_pr_003.sh` reaches its intended orchestrator assertion paths on a clean runner**
  - **Given** a clean-runner-like environment with no host global git identity
  - **When** `scripts/test_pr_003.sh` is migrated to the shared helper and executed
  - **Then** it no longer fails during sandbox repo bootstrap
  - **And** it reaches and validates the intended JIT prompt / default engine assertions

- **Scenario 3: First-wave bash contract tests remain behaviorally meaningful after migration**
  - **Given** the migrated first-wave bash tests
  - **When** they run on local and clean-runner environments
  - **Then** they still verify their original product or contract behaviors
  - **And** they do not merely pass because git bootstrap failure was masked

- **Scenario 4: First-wave mocked E2E tests no longer depend on host git identity during repo setup**
  - **Given** the migrated first-wave mocked E2E tests
  - **When** they create temporary repos and execute their setup flow in a clean-runner-like environment
  - **Then** any required setup commits succeed through the shared helper contract
  - **And** failures, if any, occur only in their intended mocked orchestration / state-machine logic

- **Scenario 5: First-wave migrated tests fail only in intended behavior paths, not at git identity bootstrap**
  - **Given** the first-wave migrated files are executed in a clean-runner-like environment with no host global git identity
  - **When** each migrated test reaches the point where it needs sandbox repo commit capability
  - **Then** the required commit bootstrap succeeds through the shared contract
  - **And** any test failure, if present, must arise only from that test’s intended product / contract / mocked-state assertions rather than missing git identity setup

- **Scenario 6: Subsequent GitHub Preflight progresses past `scripts/test_pr_003.sh`**
  - **Given** the helper-based migration has landed on the target branch
  - **When** a subsequent real GitHub-hosted `Preflight` run executes on that branch
  - **Then** `scripts/test_pr_003.sh` no longer appears as a failure item caused by sandbox git identity setup
  - **And** any remaining failure, if present, must come from its intended product/contract assertions or unrelated test surfaces

- **Scenario 7: The repository exposes a behaviorally safe shared sandbox bootstrap path for future commit-capable temp repos**
  - **Given** a future Bash or mocked E2E test that needs a temporary repo capable of making commits in a clean-runner-like environment
  - **When** that test uses the repository’s shared sandbox bootstrap contract
  - **Then** it can obtain the minimal commit-capable sandbox repo it needs without relying on host-global git identity
  - **And** the bootstrap step does not create unrequested business state or hidden side effects beyond the declared sandbox initialization contract

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是“少数脚本在 CI 上偶发 git commit 失败”，而是：

1. 测试 harness 对宿主机环境存在隐藏依赖，导致本地绿、clean runner 红；
2. repo 继续通过 one-off patch 累积散点修法，未来新增测试再次踩同类坑；
3. 修复过程中只解决 commit 能力，却没有验证测试是否真正回到 intended assertion path；
4. 为了快速 green 而削弱 contract / E2E 测试的原始意义。

### Verification Strategy

#### A. Helper-level contract verification
需要验证：
- shared helper 在 fresh HOME / 无 global git config 环境下仍能建立可提交 repo；
- helper 使用 repo-local contract，而不是宿主机配置泄漏。

#### B. First-wave test migration verification
需要验证：
- 首批迁移文件都已走统一 helper；
- 迁移后不再在 repo bootstrap 阶段失败；
- 仍然进入原本 intended product / contract assertion path。

#### C. Clean-runner parity verification
需要覆盖：
- 本地近似 clean-runner 环境（例如隔离 `HOME`）验证；
- 后续真实 GitHub-hosted Preflight run 观察是否越过对应 failure items。

#### D. Blast-radius control verification
需要验证：
- 修复集中在测试基础设施 / 测试脚本；
- 未引入无关 orchestrator 主逻辑重构；
- 未通过 skip / ignore / 弱化断言进行伪修复。

### Quality Goal
本 PRD 的质量目标不是“让某一支脚本侥幸不在 CI 报错”，而是：

> **建立一个共享、清晰、可复用的 git test sandbox initialization contract，让首批高价值测试在本地与 GitHub clean runner 上都能一致地进入真正的断言路径，从而把 Preflight 信号重新拉回到产品/契约层，而不是宿主机环境偶然性。**

## 6. Framework Modifications (框架防篡改声明)
- `scripts/e2e/setup_sandbox.sh`
- `scripts/test_pr_003.sh`
- `scripts/test_polyrepo_context.sh`
- `scripts/test_cwd_guardrail.sh`
- `scripts/test_escalation_clean.sh`
- `scripts/test_pre_commit_hook.sh`
- `scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh`
- `scripts/e2e/mocked/e2e_test_uat_orchestrator.sh`
- `scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh`
- shared git test sandbox helper file(s) required to establish the unified contract

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 先把 #29 作为单一脚本回归处理，修 `scripts/test_pr_003.sh` 的 clean-runner failure。
- **Observed correction**: 在近似 clean-runner 环境中复现后，发现 `test_pr_003.sh` 的失败先发生在 sandbox repo 的 `git commit`，根因是缺失统一的 repo-local git identity/bootstrap contract，而不是脚本业务断言本身首先坏掉。
- **v2.0 Revision Rationale**: 将方案从“单脚本补丁”升级为“共享 git test sandbox initialization helper + 首批高价值测试迁移”，避免仓库继续对宿主机 global git identity 形成系统性隐式依赖。

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
