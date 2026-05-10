---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 42 Deploy Rollback Contract Alignment for Clean Environments

## 1. Context & Problem (业务背景与核心痛点)
在 issue #40（suite contamination）与 issue #41（planner side-effects mock contract）收敛后，当前全量 `pytest tests/` 剩余失败已经稳定聚焦到 deploy / rollback 相关路径：

- `tests/test_deploy_backup.py::TestDeployBackup::test_sdlc_deploy_creates_backup`
- `tests/test_deploy_excludes.py::TestDeployExcludes::test_deploy_excludes_sdlc_runs`
- `tests/test_deploy_excludes.py::TestDeployExcludes::test_deploy_excludes_tests`
- `tests/test_pr_004_rollback.py::test_independent_symmetrical_rollbacks`

失败表象包括：
- `Releases dir not created for leio-sdlc`
- `Prod dir not created`
- `FileNotFoundError: .../.openclaw/skills/leio-sdlc/MODIFIED_MARKER`

这些失败并不指向某个孤立 assert，而是暴露了 deploy / rollback contract 在 clean environment 下没有被明确冻结，也没有在所有脚本中一致实现。当前 repo 中至少存在四类相关脚本：

- 根 skill 部署：`deploy.sh`
- kit 级部署：`kit-deploy.sh`
- sibling skill 部署：`skills/pm-skill/deploy.sh`
- rollback：`scripts/rollback.sh` 与 `skills/pm-skill/rollback.sh`

它们当前对以下关键 contract 的理解并不完全一致：
- mock HOME 与真实 HOME 的优先级
- skills 安装目录位置
- releases / backup 目录位置
- 首次部署与第二次部署后必须出现的可观察产物
- rollback 可依赖的前置结构

本 PRD 的目标不是“边跑边调查再决定 contract”，而是：

> **先冻结一套 deploy / rollback authoritative contract，再让脚本与测试围绕这套 contract 收敛。**

本 PRD 不处理：
- issue #40 的 suite contamination / `SDLC_TEST_MODE` 恢复问题；
- issue #41 的 orchestrator mock planner side-effects 问题；
- 任何与 deploy / rollback contract 无关的大规模发布架构重写。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须冻结 authoritative path-resolution order**
   - 对 deploy / rollback contract，路径优先级必须定义为：
     1. 当 `HOME_MOCK` 非空时，`HOME_MOCK` 是最高优先级，必须压过 `SDLC_RUNTIME_DIR` 与 `SDLC_SKILLS_ROOT`；
     2. 当 `HOME_MOCK` 为空时，使用 `HOME` 作为 OpenClaw 根目录推导基础；
     3. 仅在 `HOME_MOCK` 为空的非-mock 场景下，允许 `SDLC_RUNTIME_DIR` 影响 skills 安装目录；
     4. rollback 路径解析不得再单独引入与 deploy 不同的 `SDLC_SKILLS_ROOT` 语义来覆盖上述规则。

2. **必须冻结 authoritative directory layout**
   - 对于任意 skill `SLUG`，统一使用以下目录 contract：
     - `OPENCLAW_HOME = <HOME_ROOT>/.openclaw`
     - `SKILLS_DIR = <OPENCLAW_HOME>/skills`（在 `HOME_MOCK` 场景必须如此）
     - `RELEASES_ROOT = <OPENCLAW_HOME>/.releases`
     - `PROD_DIR = <SKILLS_DIR>/<SLUG>`
     - `RELEASES_DIR = <RELEASES_ROOT>/<SLUG>`
   - 其中：
     - `leio-sdlc` 的 `PROD_DIR` 必须是 `<HOME_ROOT>/.openclaw/skills/leio-sdlc`
     - `pm-skill` 的 `PROD_DIR` 必须是 `<HOME_ROOT>/.openclaw/skills/pm-skill`
     - `leio-sdlc` 的 `RELEASES_DIR` 必须是 `<HOME_ROOT>/.openclaw/.releases/leio-sdlc`
     - `pm-skill` 的 `RELEASES_DIR` 必须是 `<HOME_ROOT>/.openclaw/.releases/pm-skill`

3. **必须冻结 deploy lifecycle observables**
   - 第一次成功部署后：
     - `PROD_DIR` 必须存在；
     - `leio-sdlc` 至少可观察到 `scripts/orchestrator.py`；
     - `pm-skill` 至少可观察到 `scripts/init_prd.py`；
   - 第二次成功部署后：
     - `RELEASES_DIR` 必须存在；
     - 至少一个 `backup_*.tar.gz` 必须存在于 `RELEASES_DIR` 中；
   - 这两条是 deploy black-box contract，不允许再由 coder 自行推断。

4. **必须冻结 rollback prerequisite contract**
   - rollback 只能依赖 deploy 真正承诺的产物：
     - `PROD_DIR`
     - `RELEASES_DIR`
     - `backup_*.tar.gz`
   - rollback tests 不允许手工创建 deploy 本该生成的 skills 安装目录或 releases 目录来伪造成功前置条件。

5. **必须冻结 exclude contract**
   - deploy 最终产物中不得包含：
     - `tests/`
     - `.sdlc/`
     - `.sdlc_runs/`
   - 若当前排除逻辑实际发生在 `build_release.sh` / `.release_ignore`，则允许修改这些文件以兑现这一黑盒 contract。

6. **`pm-skill` deploy / rollback flow 必须与主 skill contract 对称**
   - `skills/pm-skill/deploy.sh` 必须和根 `deploy.sh` 共享相同路径语义；
   - `skills/pm-skill/rollback.sh` 必须和根 `scripts/rollback.sh` 共享相同 rollback 路径语义；
   - 不允许 sibling skill 使用另一套 mock HOME / skills root / releases root contract。

### Non-Functional Requirements

1. **本 PRD 可以修改脚本，但只限于 contract 对齐**
   - 允许修改 deploy / rollback 相关脚本；
   - 但不允许扩张成发布系统重构；
   - 不允许为了让测试通过而引入更多隐式路径分支。

2. **命名语义必须统一**
   - 不允许继续用含义混乱的变量名，例如把实际是 skills 路径的变量命名为 `OPENCLAW_DIR`；
   - 推荐显式区分：
     - `HOME_DIR`
     - `OPENCLAW_HOME`
     - `SKILLS_DIR`
     - `RELEASES_ROOT`
     - `PROD_DIR`
     - `RELEASES_DIR`

3. **clean environment 必须成为主验证标准**
   - 不能依赖主工作区历史残留；
   - 必须在 `HOME_MOCK` / clean worktree / GitHub clean runner 下稳定成立。

### User Stories

- **As a maintainer**, I want all deploy and rollback scripts to share one explicit path contract, so clean-environment tests and real installs observe the same artifact layout.
- **As a reviewer**, I want the PRD to freeze concrete prod/release locations up front, so the coder is not forced to guess deployment semantics mid-implementation.
- **As an engineer**, I want first deploy, second deploy, and rollback to have explicit black-box observables, so deploy/rollback tests become deterministic on clean runners.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **contract-first alignment** 路线，而不是“先调查后决定”：

- 先冻结唯一权威 contract；
- 再让所有 deploy / rollback 脚本对齐它；
- 最后让测试围绕同一 contract 收敛；
- 不通过放松断言或测试手工造目录来掩盖问题。

### 3.1 冻结的 authoritative contract

#### A. HOME root resolution
- `HOME_ROOT` 定义如下：
  - 若 `HOME_MOCK` 非空，则 `HOME_ROOT = HOME_MOCK`
  - 否则 `HOME_ROOT = HOME`

#### B. OpenClaw home and derived directories
- `OPENCLAW_HOME = "$HOME_ROOT/.openclaw"`
- `RELEASES_ROOT = "$OPENCLAW_HOME/.releases"`
- 当 `HOME_MOCK` 非空时：
  - `SKILLS_DIR = "$OPENCLAW_HOME/skills"`
- 当 `HOME_MOCK` 为空时：
  - `SKILLS_DIR = "${SDLC_RUNTIME_DIR:-$OPENCLAW_HOME/skills}"`

#### C. Skill-specific directories
- 对任意 skill `SLUG`：
  - `PROD_DIR = "$SKILLS_DIR/$SLUG"`
  - `RELEASES_DIR = "$RELEASES_ROOT/$SLUG"`

#### D. Backup contract
- 第二次部署成功后，必须在 `RELEASES_DIR` 中存在至少一个：
```text
backup_<YYYYMMDD_HHMMSS>.tar.gz
```

### 3.2 具体改动方向

#### A. `deploy.sh`
必须改到与上述 contract 一致：
- `HOME_MOCK` 场景下不得再让 `SDLC_RUNTIME_DIR` 抢占 `SKILLS_DIR`
- 统一命名为 `OPENCLAW_HOME` / `RELEASES_ROOT`
- 首次 deploy 保证 `PROD_DIR` 存在
- 第二次 deploy 保证 `RELEASES_DIR` 与 backup tarball 存在

#### B. `skills/pm-skill/deploy.sh`
必须与根 `deploy.sh` 对齐：
- 增加 `cd "$(dirname "$0")" || exit 1`
- 采用同样的 `HOME_ROOT` / `OPENCLAW_HOME` / `SKILLS_DIR` / `RELEASES_ROOT` 逻辑
- 保证 `pm-skill` 的 `PROD_DIR` 与 `RELEASES_DIR` 按冻结 contract 落位
- 保留 `agent_driver.py` / `utils_notification.py` bundling，但其产物位置必须符合上述 contract

#### C. `scripts/rollback.sh`
必须与 deploy 共享同一套路径语义：
- 删除当前混乱的 `OPENCLAW_DIR = .../.openclaw/skills` 语义
- 使用：
  - `HOME_ROOT`
  - `OPENCLAW_HOME`
  - `SKILLS_DIR`
  - `RELEASES_ROOT`
  - `PROD_DIR`
  - `RELEASES_DIR`
- rollback 仅从 `RELEASES_DIR` 查找 `backup_*.tar.gz`
- lock guardrail 逻辑保持不变

#### D. `skills/pm-skill/rollback.sh`
必须与 `scripts/rollback.sh` 对称：
- 采用同样的 `HOME_ROOT` / `OPENCLAW_HOME` / `SKILLS_DIR` / `RELEASES_ROOT` / `PROD_DIR` / `RELEASES_DIR` contract
- 不允许继续保留与主 rollback 不一致的 `SDLC_SKILLS_ROOT` 覆盖语义

#### E. `kit-deploy.sh`
可以保持 orchestrator 角色，但必须保证：
- 它调用的所有 skill deploy scripts 都服从同一 contract；
- 如需要，可增加轻量一致性日志，但不要求大改结构。

#### F. Release build / exclude surface
如果为了兑现 `tests/`、`.sdlc/`、`.sdlc_runs/` 排除 contract，发现问题实际位于：
- `scripts/build_release.sh`
- `.release_ignore`

则授权修改它们，但仅限兑现本 PRD 明确写死的 exclude contract。

### 3.3 明确不采用的方案

1. **不允许 coder 自行再决定 contract**
   - 本 PRD 已经写死路径优先级、目录布局和生命周期可观察产物；
   - coder 不得把关键 contract 重新变回“审一审再说”。

2. **不只改 assert**
   - 不能仅通过删掉 `Prod dir not created` / `Releases dir not created` 来收口。

3. **不让测试手工补目录来假装 deploy 成功**
   - rollback tests 不能自己 mkdir 出 deploy 应生成的目录结构。

4. **不扩张成发布系统大重构**
   - 目标是 contract 对齐，不是重写 deploy framework。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: first deploy of `leio-sdlc` uses the frozen HOME-root contract**
  - **Given** a clean temporary environment with `HOME_MOCK=<mock_home>`
  - **When** `deploy.sh --no-restart` succeeds for the first time
  - **Then** `leio-sdlc` is installed at:
```text
<mock_home>/.openclaw/skills/leio-sdlc
```
  - **And** that directory contains `scripts/orchestrator.py`

- **Scenario 2: second deploy of `leio-sdlc` creates the frozen backup layout**
  - **Given** a successful first deploy under `HOME_MOCK=<mock_home>`
  - **When** `deploy.sh --no-restart` succeeds a second time
  - **Then** the following directory exists:
```text
<mock_home>/.openclaw/.releases/leio-sdlc
```
  - **And** it contains at least one file matching:
```text
backup_*.tar.gz
```

- **Scenario 3: `pm-skill` deploy follows the same frozen contract**
  - **Given** a clean temporary environment with `HOME_MOCK=<mock_home>`
  - **When** `skills/pm-skill/deploy.sh --no-restart` succeeds
  - **Then** `pm-skill` is installed at:
```text
<mock_home>/.openclaw/skills/pm-skill
```
  - **And** second deploy creates:
```text
<mock_home>/.openclaw/.releases/pm-skill/backup_*.tar.gz
```
  - **And** `<mock_home>/.openclaw/skills/pm-skill/scripts/agent_driver.py` exists

- **Scenario 4: excluded content is absent from deployed `leio-sdlc` production directory**
  - **Given** source-side directories `tests/`, `.sdlc/`, and `.sdlc_runs/`
  - **When** `deploy.sh --no-restart` completes successfully
  - **Then** the deployed `PROD_DIR` does not contain:
```text
tests/
.sdlc/
.sdlc_runs/
```

- **Scenario 5: rollback consumes real deploy-generated artifacts only**
  - **Given** `kit-deploy.sh` has completed twice successfully under `HOME_MOCK=<mock_home>`
  - **When** `scripts/rollback.sh` and `skills/pm-skill/rollback.sh` execute
  - **Then** they succeed using backup tarballs from:
```text
<mock_home>/.openclaw/.releases/<slug>/backup_*.tar.gz
```
  - **And** they restore the corresponding production directories under:
```text
<mock_home>/.openclaw/skills/<slug>
```
  - **And** manually inserted `MODIFIED_MARKER` files are removed after rollback

- **Scenario 6: clean worktree and GitHub clean runner observe the same layout**
  - **Given** a clean temporary worktree or GitHub Actions runner
  - **When** deploy/rollback tests execute
  - **Then** they pass without depending on pre-existing local machine state outside the frozen contract above

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本 PRD 最大风险不是小的路径拼接错误，而是：

1. 继续允许脚本和测试各自理解一套目录 contract；
2. 在 mock HOME 场景下仍让 runtime 环境变量抢占技能安装根路径；
3. 通过放松测试而不是修正 contract 来掩盖真实 deploy/rollback 问题；
4. sibling skill（`pm-skill`）路径语义不对称，导致 `kit-deploy` / rollback 只有一半可信。

### Verification Strategy

#### A. Focused failing-test verification
必须显式运行：
- `pytest -q tests/test_deploy_backup.py`
- `pytest -q tests/test_deploy_excludes.py`
- `pytest -q tests/test_pr_004_rollback.py`

#### B. Clean-environment verification
必须在以下环境之一重复验证：
- 独立临时 worktree
- 临时 `HOME_MOCK`
- GitHub Actions clean runner

#### C. Full-suite regression check
修复后应再次运行：
- `pytest tests/`

目标是让 deploy/rollback 组不再是全量剩余失败来源。

#### D. No fake deploy success
任何 rollback 相关测试不得手工补出 deploy 本应生成的 prod/release 目录；必须以真实 deploy 结果为前置。

## 6. Framework Modifications (框架防篡改声明)
本 PRD 允许修改以下与 deploy / rollback contract 直接相关的文件：
- `deploy.sh`
- `kit-deploy.sh`
- `skills/pm-skill/deploy.sh`
- `scripts/rollback.sh`
- `skills/pm-skill/rollback.sh`
- `scripts/build_release.sh`（如确有必要以兑现 exclude contract）
- `.release_ignore`（如确有必要以兑现 exclude contract）
- `tests/test_deploy_backup.py`
- `tests/test_deploy_excludes.py`
- `tests/test_pr_004_rollback.py`
- 必要的测试辅助文件

本 PRD **不授权**修改以下与其它 issue 边界相关的内容：
- `scripts/orchestrator.py`
- `tests/test_spawn_auditor.py`
- `tests/test_thinking_e2e_convergence.py`
- `tests/test_thinking_orchestrator_primary.py`
- `tests/test_orchestrator_session_strategy.py`
- 与 #40 / #41 相关的测试修复逻辑

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初版将 #42 定义为 deploy / rollback tests 在 clean environment 下暴露出的 contract drift 问题。
- **v1.1 Scope Decision**: 明确 #42 与 #40 / #41 分离；#42 只处理 deploy / rollback contract。
- **v1.2 Strategy Decision**: 初版采用“先审并统一 runtime contract，再修测试对齐”的模糊表达，被 Auditor 拒绝。
- **v1.3 Contract Freeze**: 明确冻结 `HOME_MOCK` / `HOME` / `SDLC_RUNTIME_DIR` 的优先级、prod dir 精确位置、release/backup 精确布局，以及 `pm-skill` 的对称 contract。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- None
