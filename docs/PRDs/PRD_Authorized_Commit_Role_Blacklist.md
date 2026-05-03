---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Authorized Commit Role Blacklist

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前已经有基于 Git hook 的直接提交防线，但这条防线的核心豁免机制仍然过于粗粒度：只要通过 `git -c sdlc.runtime=1 ...` 进入运行时豁免路径，就可能绕过 protected branch 上的普通提交拦截。

这在大多数合法系统路径上是必要的，因为以下路径本来就需要保留提交能力：
- Coder 在执行中的合法代码提交
- `merge_code.py` 的系统级 merge
- `commit_state.py` 对 `STATE.md` / `docs/PRDs/*.md` 的管理性提交
- Orchestrator 在极少数控制面恢复/法证场景下的系统级提交

但 `ISSUE-1186` 暴露出一个更危险的问题：

> 当前机制并没有显式区分“谁”在使用 `sdlc.runtime=1` 豁免。

也就是说，某些本来绝不应该拥有提交能力的执行角色（例如 Verifier / Reviewer / Auditor / Planner）如果意外进入运行时豁免路径，就可能尝试提交代码或绕过正常 SDLC 审查路径。这不是普通代码质量问题，而是治理边界问题。

这里必须明确一个现实前提：

> 本 PRD **并不声称**能够构建一个不可伪造、完美防御、能够彻底阻挡恶意 Agent 的强授权系统。

在当前 OpenClaw / agent 执行模型下，Agent 理论上仍可能：
- 观察实现细节
- 猜测 allowlist 中的 role 名称
- 主动伪造 `sdlc.role`
- 尝试绕过普通约束

Boss 当前要求解决的不是这个最终形态问题，而是一个**第一阶段、可落地、低复杂度的治理止血问题**：
- 让系统从“完全没有角色语义的 runtime commit 豁免”升级到“有统一 helper + role + hook 协议”的状态；
- 让明显不该 commit 的执行角色在正常路径下先被粗粒度拦住；
- 让提交行为有更清晰的检测面和审计信号，便于后续 Auditor 和人类继续收紧；
- 明确接受：这不是完美阻断，只是初步可用的 policy tripwire / governance seam。

Boss 已明确选择一个**更小 scope 的第一阶段修复**：
- **不尝试物理阻止非-Coder Agent 修改工作区文件**；
- **不尝试在本 PRD 内构建可信身份签发或不可伪造授权体系**；
- **只解决提交权限问题**；
- **沿用现有 `sdlc.runtime` 机制**；
- **新增 `role` 概念，并通过 allowlist 只授权极少数合法 commit 角色**；
- **目标是先快速止血，避免误杀合法的 orchestrator / merge / state 提交路径。**

本 PRD 只做这一件事：

> 在保留现有 runtime commit 豁免模型的前提下，引入显式 `sdlc.role`，并把 commit 授权边界收口为 helper + allowlist。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. 所有通过运行时豁免路径触发的 Git commit / merge 类操作，必须显式携带 `sdlc.role`。
2. 现有 `sdlc.runtime=1` 机制必须保留，避免破坏现有 orchestrator / merge / state 管理流程。
3. 必须引入一个**极小的统一 helper / wrapper** 来构造“授权的 runtime commit 上下文”，而不是在各调用点重复手写 `-c sdlc.runtime=1 -c sdlc.role=...`。
4. Git pre-commit 防线必须在检测到 `sdlc.runtime=1` 时，进一步读取 `sdlc.role`。
5. 只有显式位于 allowlist 中的角色，才能继续使用 runtime commit 豁免。
6. 第一阶段 allowlist 必须至少覆盖以下合法角色：
   - `coder`
   - `orchestrator`
   - `merge_code`
   - `commit_state`
7. 所有不在 allowlist 中的角色都必须被拒绝，包括但不限于：
   - `verifier`
   - `reviewer`
   - `auditor`
   - `planner`
   - `arbitrator`
   - `unknown`
8. 合法系统提交路径必须继续可用，不得被误杀；本次授权边界必须严格收口到 allowlist 集合。
9. `merge_code.py` 必须通过统一 helper 显式声明自己的 system role，而不是隐式依赖“只要 runtime 就能过”。
10. `commit_state.py` 必须通过统一 helper 显式声明自己的 system role，而不是隐式依赖“只要 runtime 就能过”。
11. Orchestrator 自己的合法系统提交路径（如恢复/法证相关提交）必须通过统一 helper 显式声明 `orchestrator` role。
12. 任何未来如果新增 runtime commit 路径，也必须遵循“显式 role + 统一 helper”约束；缺失 role 时应默认按非授权路径处理。
13. 标准 pre-commit hook 必须携带可机读的 hook 元数据，至少包括独立的 `SDLC_HOOK_SCHEMA_VERSION`。
14. `doctor.py` 必须把该 hook 视为项目 SDLC 基础设施协议的一部分，并支持检查/自动升级该 hook 版本。
15. hook 是否需要升级，必须以独立的 hook schema version 为准，而不是直接等同于当前 `leio-sdlc` runtime skill 版本。

### Non-Functional Requirements
1. 本次修复必须保持为**最小止血范围**，不得扩张成文件系统只读、workspace diff 白名单、沙箱隔离、artifact-only mount 等更大设计。
2. 本次不重做权限体系；只在现有 `sdlc.runtime` 基础上增加 `sdlc.role` 维度。
3. 本次不处理“非-coder agent 修改了未提交代码但未 commit”的问题；那属于后续阶段。
4. 本次必须优先保证**不误杀现有合法系统路径**。
5. 本次必须优先保证 hook 逻辑简单、可读、可测试，不引入复杂策略引擎。
6. hook 协议升级必须支持原子化 rollout：不得只发布新 hook 而不同时发布 helper 与官方 runtime commit 调用点更新。
7. 本次方案在安全模型上被明确定义为**粗粒度 policy tripwire**，而不是可信身份系统、不可伪造授权系统或完美防御系统。
8. 本次允许“理论上可被更高能力/恶意 agent 伪造 role 绕过”的残余风险继续存在；该残余风险必须在 PRD 中被明确承认，而不是被隐含否认。
9. 本次交付价值应体现在：提高正常路径下的阻拦率、减少误用、增强审计信号，而不是声称彻底消灭越权提交风险。

### Explicit Non-Goals
1. **Not a trusted identity system**：本 PRD 不负责建立可信身份签发、签名、不可伪造 token、capability registry 或其他强身份认证机制。
2. **Not a perfect authorization boundary**：本 PRD 不承诺阻止高能力或恶意 Agent 主动伪造 allowlist role。
3. **Not filesystem isolation**：本 PRD 不提供只读挂载、无 `.git` 工作区、容器隔离、shadow repo 或 artifact-only write sandbox。
4. **Not post-run tamper detection**：本 PRD 不实现非-coder agent 的 workspace diff 审计或非法工作区改动报警。
5. **Not a full governance closure for ISSUE-1186**：本 PRD 只交付第一阶段的粗粒度 commit 阻拦与审计信号增强，不解决 1186 的所有长期治理问题。

### User Stories
- 作为 Boss，我希望 Verifier / Reviewer / Auditor / Planner 即使进入 runtime 路径，也能在正常路径下先被粗粒度拦住，不再像现在这样默认与合法系统提交路径混在一起。
- 作为系统维护者，我希望保留 orchestrator / merge_code / commit_state 的合法提交能力，不因为修复 1186 而打断正常 SDLC。
- 作为治理层，我希望提交能力不再只是“是否 runtime”，而是“runtime + 明确角色 + 显式 allowlist 授权”，即使这仍然不是不可伪造的强身份系统。
- 作为审计者，我希望未来看到一次 runtime commit 时，至少能知道它声称的角色语义，并把它作为后续 Auditor / 人类判断的检测信号。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Design Choice
本次采用：

> **保留现有 `sdlc.runtime` 豁免 + 新增 `sdlc.role` + helper 强制 role + hook allowlist 授权**

但必须明确：

> 这里的 allowlist 是一个**第一阶段的粗粒度提交策略收口点**，不是可信身份认证系统。

它的预期价值是：
- 把原本匿名的 runtime commit 豁免收敛成更清晰的协议；
- 让大部分正常/误用路径在第一时间被拦下；
- 给 Auditor 与人类留下更强的治理与检测信号。

它**不承诺**解决：
- 恶意 agent 主动伪造 allowlist role
- 高对抗场景下的不可伪造身份传播
- 完整 capability signing / token registry
- 完美的强安全授权边界

而不采用：
- 只允许 coder 的极端白名单（会误伤 orchestrator / merge_code / commit_state）
- 完整 capability model
- 文件系统只读或 repo 隔离
- 非-coder post-run workspace 审计

### 3.2 Why Allowlist Now Becomes Viable
本次最终选择 **role allowlist**，不再使用 blacklist，原因是：
1. 在旧模型里，各调用点散落手写 runtime 参数，commit 豁免路径是开放且不可枚举的，因此直接 allowlist 风险高；
2. 本 PRD 已经引入一个统一 helper，并要求所有官方 runtime commit 路径都必须通过 helper 生成身份参数；
3. 一旦 helper 成为唯一官方 runtime commit 接缝，系统的 commit 授权边界就从“开放世界”收口成“可枚举的有限集合”；
4. 在这个前提下，hook 现在可以安全采用 closed-world / fail-closed 授权模型：只有 allowlist 中明确列出的角色被允许，其他角色（包括未来新增、错拼、临时 role）一律拒绝；
5. 这正符合 Least Privilege、Single Authorization Seam、Fail-Closed Policy Boundary 的治理目标。

### 3.3 Expected Role Model
所有运行时 commit/merge 路径都要显式设置角色语义，但**不在各调用点直接手写运行时 git 参数**，而是统一通过一个极小 helper / wrapper 生成。

本 PRD 明确承认的官方 commit 授权角色只有：
- `coder`
- `orchestrator`
- `merge_code`
- `commit_state`

以下角色明确不具备 commit 授权资格：
- `reviewer`
- `verifier`
- `auditor`
- `planner`
- `arbitrator`
- `unknown`

任何未来新增角色，如果未被显式加入 allowlist，都必须默认拒绝。

### 3.4 Authorized Runtime Commit Helper
本次不做完整 VCS 抽象层，但要引入一个**最小统一封装点**，用于构造“授权的 runtime commit 上下文”。

Git 下的推荐形态可以是一个很小的 helper，例如：
- `runtime_git_identity_args(role)`
- `build_runtime_git_config(role)`
- 或同等粒度的统一封装

其职责仅限于：
1. 生成当前 Git 实现下所需的 runtime 豁免参数；
2. 强制要求显式 role；
3. 让 `merge_code.py`、`commit_state.py`、`orchestrator.py` 以及其他未来官方 runtime commit 路径，都通过同一处生成提交身份参数；
4. 为未来切换到其他代码管理系统（VCS decoupling）保留一个单一替换接缝。

当前 Git 实现下，该 helper 预期会统一生成等价于：
- `-c sdlc.runtime=1`
- `-c sdlc.role=<role>`

但 PRD 明确要求：
> 调用点不应再各自散落手写这组参数；必须通过统一 helper 输出。

### 3.5 Hook Enforcement Strategy
当前 `.sdlc_hooks/pre-commit` 逻辑是：
- protected branch 上普通 commit 禁止
- `sdlc.runtime=1` 或 override 时允许

本次要改成：
1. 如果没有 runtime 豁免：维持现有保护逻辑
2. 如果有 `sdlc.runtime=1`：
   - 读取 `sdlc.role`
   - 若 role 缺失，则视为 `unknown`
   - 只有 role 位于 allowlist 中时才允许继续
   - role 不在 allowlist 中时必须拒绝提交
3. 如果 runtime 路径缺少 `sdlc.role`：按 `unknown` 角色 fail closed，防止“匿名 runtime 豁免”继续存在
4. 由于所有官方 runtime commit 路径都被要求经过 helper，因此 allowlist 授权现在具备工程上的可枚举性，不再依赖开放式 blacklist 维护。

### 3.6 Hook Versioning & Doctor Upgrade Strategy
本次 hook 协议不应继续是“只有文件存在与否”的隐式状态，而应有显式版本元数据。

推荐在标准 hook 顶部加入可机读字段，例如：
- `SDLC_MANAGED_HOOK=leio-sdlc`
- `SDLC_HOOK_SCHEMA_VERSION=<integer>`
- `SDLC_SOURCE_RUNTIME_VERSION=<runtime version>`（可选，用于追溯来源）

其中：
- `SDLC_HOOK_SCHEMA_VERSION` 是 **doctor 判定是否需要升级的权威字段**；
- `SDLC_SOURCE_RUNTIME_VERSION` 只是 provenance 元数据，不应单独作为升级判据；
- hook schema version 必须独立于整体 runtime skill version 维护，避免因为 runtime 里无关改动而误触发项目级 hook 升级。

`doctor.py` 的职责边界在本 PRD 中明确为：
1. `--check` 时检查目标项目 hook 是否存在；
2. 若 hook 缺失版本字段，则视为旧协议；
3. 若 `SDLC_HOOK_SCHEMA_VERSION` 小于当前 runtime 期望值，则报告需要升级；
4. `--fix` 时将目标项目 hook 自动升级为当前 runtime 自带的标准 hook；
5. `doctor.py` 只负责 hook 协议的项目级自动升级，不负责修改业务项目源码中的 commit 调用点；
6. 官方 runtime commit 路径的 helper 接入必须由 `leio-sdlc` 自身代码变更完成，而不是依赖 doctor 猜测和改写调用点；
7. 在本 PRD 目标达成后，项目侧运行一次 `doctor.py --fix <target_dir>` 应能把对应项目的 managed hook 自动升级到当前 runtime 的标准 hook版本。

### 3.7 Rollout Constraint
本次变更必须原子化发布以下内容：
1. 新的 runtime commit helper
2. 所有官方 runtime commit 调用点的 helper 接入
3. 新版标准 pre-commit hook
4. `doctor.py` 对 hook schema version 的检查与 `--fix` 自动升级能力

本 PRD 不授权“只升级 hook、不升级调用点”的半发布方式。

### 3.8 Files / Modules in Scope
优先修改：
- `.sdlc_hooks/pre-commit`
- `scripts/merge_code.py`
- `scripts/commit_state.py`
- `scripts/orchestrator.py`（仅限其官方系统提交路径接入统一 helper）
- `scripts/doctor.py`
- `scripts/agent_driver.py`（如需要统一 role 传递约定）
- 新增或提取一个极小的 runtime git identity helper（文件位置由实现决定，但必须保持低复杂度）
- 相关测试文件（hook / merge / state commit / runtime role regression / doctor hook-version upgrade）

如各 spawn 脚本需要补 role 语义，也仅做最小必要改动，不扩展到更大运行时安全重构。

### 3.9 Explicit Out-of-Scope
本 PRD 明确不做：
- 不做非-coder workspace diff 审计
- 不做 artifact-only whitelist
- 不做只读挂载 / 无 `.git` workspace
- 不做 capability token / permission registry
- 不做第二阶段“发现非法工作区改动立即报警”的机制
- 不修复 1186 的全部长期治理问题，只做第一阶段 commit blacklisting

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: blacklisted runtime role is rejected on commit**
  - **Given** a repository with the SDLC pre-commit hook installed and runtime bypass enabled via `sdlc.runtime=1`
  - **And** the commit is executed with `sdlc.role=verifier`
  - **When** a commit is attempted
  - **Then** the pre-commit hook must reject the commit
  - **And** the rejection message must clearly indicate that the role is not authorized to commit

- **Scenario 2: another blacklisted analysis role is rejected on commit**
  - **Given** a repository with the SDLC pre-commit hook installed and runtime bypass enabled via `sdlc.runtime=1`
  - **And** the commit is executed with `sdlc.role=reviewer` or `auditor` or `planner` or `arbitrator`
  - **When** a commit is attempted
  - **Then** the commit must be rejected

- **Scenario 3: authorized system merge path still works**
  - **Given** a reviewed feature branch that is ready for merge
  - **And** `merge_code.py` executes its runtime Git merge path through the unified runtime commit helper with `merge_code` role
  - **When** merge is attempted
  - **Then** the merge must still succeed
  - **And** the blacklist rule must not falsely block it

- **Scenario 4: authorized state-management path still works**
  - **Given** a valid `STATE.md` or PRD administrative update
  - **And** `commit_state.py` performs its runtime commit path through the unified runtime commit helper with `commit_state` role
  - **When** the management commit is attempted
  - **Then** the commit must still succeed

- **Scenario 5: authorized coder path is not blocked**
  - **Given** a normal code-change flow under the Coder role
  - **And** runtime Git commit is performed through the unified runtime commit helper with `coder` role
  - **When** the commit is attempted
  - **Then** the commit must not be rejected by the blacklist rule

- **Scenario 6: anonymous runtime bypass is no longer accepted**
  - **Given** a runtime commit attempt using `sdlc.runtime=1`
  - **And** no `sdlc.role` is provided
  - **When** the commit is attempted
  - **Then** the hook must treat the runtime caller as `unknown`
  - **And** the commit must be rejected
  - **And** the rejection must indicate that runtime commits require an explicit role

- **Scenario 7: doctor detects outdated managed hook**
  - **Given** a target repository with an installed managed SDLC hook
  - **And** the hook either lacks `SDLC_HOOK_SCHEMA_VERSION` or has a lower schema version than the current runtime expects
  - **When** `doctor.py --check` is executed
  - **Then** the project must be reported as non-compliant
  - **And** the output must indicate that the managed hook requires upgrade

- **Scenario 8: doctor auto-upgrades managed hook**
  - **Given** a target repository with an outdated managed SDLC hook
  - **When** `doctor.py --fix` is executed
  - **Then** the hook must be replaced with the current runtime’s standard hook
  - **And** the upgraded hook must contain the expected `SDLC_HOOK_SCHEMA_VERSION`
  - **And** a project that previously failed the hook version check must pass the hook compliance check after the fix

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险只有两个：
1. **止血失败**：Verifier / Reviewer / Auditor / Planner 仍可借 runtime 豁免直接 commit
2. **误杀合法路径**：Merge / state management / coder 被新规则错误拦截

测试策略：
- 以**hook 行为测试 + 最小回归脚本**为主
- 不需要整条真实 SDLC E2E
- 必须覆盖：
  - 非 allowlist 角色 commit 被拒绝
  - coder 被允许
  - merge_code 被允许
  - commit_state 被允许
  - 缺失 role 的 runtime commit 被拒绝
  - 官方 runtime commit 路径确实通过统一 helper 生成身份参数，而不是散落手写
  - doctor 能识别缺失/过旧 hook 版本
  - doctor --fix 能自动升级 managed hook
- 可以使用临时 git 仓库 + hooksPath 的快速测试方式
- 如已有 `test_pre_commit_hook.sh`，优先扩展而不是新造一套测试框架

质量目标：
- 非 allowlist 角色不能再通过 runtime commit 豁免写入 git 历史
- 合法系统路径零误杀
- runtime commit 身份参数生成逻辑有单一封装点，便于后续对接非 Git 的代码管理系统
- hook 协议可被 doctor 显式检查和自动升级
- hook 规则清晰、稳定、可审计

## 6. Framework Modifications (框架防篡改声明)
本 PRD 明确授权修改以下框架文件：
- `.sdlc_hooks/pre-commit`
- `scripts/merge_code.py`
- `scripts/commit_state.py`
- `scripts/orchestrator.py`
- `scripts/doctor.py`
- `scripts/agent_driver.py`（仅限最小必要的 role 传递约定）
- `scripts/test_pre_commit_hook.sh`
- 与上述行为直接相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初始讨论方向是“让 UAT / verifier 真正物理只读”，包括只读挂载、artifact-only 输出路径、post-run diff 审计等。
- **v1.1**: Boss 明确要求缩 scope：当前阶段不追求防止非-coder agent 修改工作区文件；只需要禁止它们 commit，并在不误杀合法系统路径的前提下先完成第一阶段止血。
- **v1.2**: 曾尝试采用 blacklist 方案：保留现有 `sdlc.runtime` 豁免机制，新增一个极小统一 helper 来生成 runtime commit 身份参数，并在 hook 中通过 role blacklist 拦截高风险角色，避免误伤 orchestrator / merge / state 管理提交，同时为未来 VCS decoupling 保留单一替换接缝。
- **Audit Rejection (v1.2)**: Auditor 否决 blacklist 授权模型，理由是 commit 权限属于核心治理边界，blacklist 仍然是开放式授权：未来新增 role、临时 role、错拼 role 都可能被默认放行，不符合 least-privilege / fail-closed 要求。
- **v1.3**: 由于本 PRD 已要求所有官方 runtime commit 路径统一经过 helper，系统已经具备可枚举的官方授权集合，因此鉴权模型收口为 allowlist：仅 `coder`、`orchestrator`、`merge_code`、`commit_state` 允许 commit，其他任何 role 一律拒绝。
- **v1.4**: 补齐 rollout 闭环：hook 版本必须独立编号，doctor 必须负责检查和自动升级项目 hook 协议；升级判据基于 `SDLC_HOOK_SCHEMA_VERSION`，而不是简单绑定整体 runtime skill 版本。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **For managed hook metadata header (exact lines in standard hook)**:
```text
# SDLC_MANAGED_HOOK=leio-sdlc
# SDLC_HOOK_SCHEMA_VERSION=2
```

- **For unauthorized non-allowlisted runtime role commit rejection**:
```text
❌ Commit rejected: SDLC runtime role '<ROLE>' is not authorized to commit.
```

- **For missing runtime role on privileged commit path**:
```text
❌ Commit rejected: runtime commit requires explicit sdlc.role.
```
