---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 57 Controlled Python Execution and Runtime Contract

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前在 Python 执行模型上仍然更接近“被复制/调用的一组脚本”，而不是一个具有明确开发环境、测试环境、部署运行环境边界的受控 Python 应用。该状态在仅依赖标准库或宿主机偶然已具备依赖时尚可勉强工作，但一旦引入额外 Python 依赖，就会暴露出系统性问题：

1. 当前仓库缺少明确、唯一、可审计的 Python execution contract，导致开发时、测试时、部署后 skill runtime 执行时到底使用哪个 Python 环境并不清楚。
2. 当前运行方式对 system Python 与当前 shell 状态存在隐式依赖；在出现 PEP 668 externally managed 环境时，直接全局 `pip install` 不再是安全或可移植的假设。
3. 即使本地开发 shell 中临时可运行，也不能推出部署到 `~/.openclaw/skills/...` 后的 skill runtime 一定可运行；开发成功与运行时成功之间缺少正式契约。
4. 当前 deploy 更接近“复制文件”，而不是“交付一个带有可验证运行环境的 Python skill/app 实例”，因此无法保证第三方依赖在运行时真实可用。
5. GitHub CI 目前也缺少与未来本地/runtime execution model 一致的明确约束，存在“CI 绿但本地/运行时环境不一致”或反向漂移风险。
6. Issue #50 已明确依赖一个受控、明确、可重复的 Python execution context。若不先建立该基础，后续 ACP 相关 Python 依赖与 runtime 验证工作将持续被环境不确定性污染。

本 PRD 的目的不是解决 ACP 本身，也不是定义最终的安装/分发/ClawHub 模型，而是先为 `leio-sdlc` 建立一个本地开发、测试、部署后 runtime、以及 GitHub CI 可共同依赖的受控 Python execution/runtime contract。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 系统必须为 `leio-sdlc` 定义一个唯一、明确、可审计的 Python dependency entry，且本 issue 将其正式钉死为仓库根目录下的 `requirements.txt`。
2. 系统必须为 `leio-sdlc` 定义一个受控的开发/测试 Python execution context，用于本地开发、测试、验证命令执行。
3. 系统必须为部署后的 `leio-sdlc` skill runtime 定义一个受控的运行时 Python execution context，不得默认依赖 system Python 全局包状态。
4. 系统必须明确开发 execution context 与 runtime execution context 的关系与边界，禁止把“当前 shell 恰好可用”视为正式契约；本 issue 采用双环境模型：开发/测试使用 repo 内 execution context，部署后 runtime 使用独立 runtime execution context。
5. 系统必须提供一种无需依赖人肉记忆 `source .venv/bin/activate` 的执行方式，使常见开发/测试命令显式落到正确的 Python execution context。
6. 系统必须使部署后 skill 脚本通过显式受控的 Python 解释器执行，而不是默认裸用 `python3` 或 system Python。
7. 系统必须让 deploy 过程具备最小 runtime provisioning 能力，至少包括：在 staging release 中创建或校验 runtime execution context、从唯一依赖入口安装/同步依赖、执行最小 import smoke、并执行至少一次 skill 启动级 smoke validation；只有全部通过后才允许进行 atomic swap。
8. 系统必须提供最小 smoke validation，用于验证部署后的 `leio-sdlc` skill runtime 确实运行在预期 execution context 上。
9. 系统必须使 GitHub CI 使用与本地/运行时契约一致的受控 Python execution model，而不是依赖宿主机偶然状态。
10. 系统必须保证该 execution/runtime contract 不会隐式污染或接管其他不属于 `leio-sdlc` 的 skill 执行环境。
11. 系统必须明确收敛所有 contract-critical `python3` 执行路径，至少包括：正式开发/测试入口、deploy/runtime 启动入口、GitHub CI 默认路径、以及与 execution contract 直接相关的 smoke/tests；这些路径若不修正将被视为本 issue 未完成。
12. 系统必须同步更新当前正式生效的开发/运行相关文档、提示与入口说明（包括但不限于当前生效的 `SKILL.md`、hooks、JIT 提示、README 或等价正式入口文档），使其与新的 execution contract 一致；历史归档文档不在本 issue 阻塞范围内。
13. 系统必须把本 issue 限定在本地开发、测试、部署后 runtime、以及 GitHub CI 所需的 execution contract；更广义的安装/分发/Hub 兼容问题不属于本 issue 的完成条件。
14. 系统必须把 contract-non-critical 的 `python3` 残留引用（如历史文档、归档 PRD、非默认 mocked/e2e、模板与参考材料）视为后续清理项，而不是本 issue 的阻塞范围。

### 2.2 Non-Functional Requirements
1. 该实现必须优先追求可重复、可审计、可重建，而不是依赖当前机器偶然状态。
2. 该实现必须避免要求 coder 直接修改 system Python 全局包状态作为交付前提。
3. 该实现必须避免把“手工 source 某个 shell 环境”作为唯一正确使用方式；正式契约应依赖显式解释器、包装器、脚本入口或等价机制，而不是人脑记忆。
4. 该实现必须保持对现有其他 skill 的隔离性，不得把 `leio-sdlc` 的 execution context 设计成默认全局共享环境。
5. 该实现必须把 scope 有界在 execution/runtime contract，不得在本 issue 内扩张为完整安装/分发/ClawHub packaging 工程。
6. 该实现必须允许后续 issue 在此基础上增加 Python 依赖（如 ACP SDK）而不再反复争论执行环境归属。
7. 该实现必须与当前 `leio-sdlc` 官方 baseline / deploy / CI 流程兼容演进，不得通过一次性临时脚本绕过正式流程。
8. 本 issue 不要求所有开发者都必须在交互 shell 中手工执行 `source .venv/bin/activate`；只要求所有正式开发/测试/运行命令最终显式落到正确 execution context。
9. 选择 `requirements.txt` 作为唯一依赖入口的原因是：本 issue 目标是以最小迁移成本尽快收敛 execution/runtime contract，而不是同步引入更大范围的 Python packaging/metadata 结构迁移。

### 2.3 Responsibility Boundary
#### Coder Responsibilities
1. coder 负责在仓库内落地唯一 Python dependency entry，并将本 issue 需要的依赖管理收敛到该入口。
2. coder 负责落地开发/测试 execution context 的命令入口约束，使标准开发/测试命令显式使用正确的 Python execution context。
3. coder 负责落地 deploy/runtime 侧的 Python 解释器绑定、最小 runtime provisioning 脚本化能力，以及对应 smoke validation。
4. coder 负责更新 GitHub CI，使其与本地/运行时 execution contract 对齐。
5. coder 负责提供与 execution/runtime contract 直接相关的最小测试、fixture、回归保护与文档化入口。

#### Environment / Operator Responsibilities
1. 环境侧负责提供目标机可用的基础 Python 能力、可创建 execution context 的权限前提，以及本 issue 所需的基础运行前提。
2. 环境侧负责执行首次环境级 adopt / rollout 验证，确认新 contract 在目标环境中可被接受与使用。
3. 环境侧负责本 issue 范围外的安装/分发/ClawHub 相关策略与后续演进决策。
4. 环境侧的一次性手工准备只用于提供前置能力，不得被视为 coder 交付本身的一部分，也不得替代 repo/deploy/CI 中应正式固化的 execution/runtime contract。

### 2.4 Explicit Non-Goals
本 PRD 不包含以下目标：
- 定义 `leio-sdlc` 的最终 ClawHub / Hub-style 安装与分发契约
- 把 `leio-sdlc` 完整改造成公开发布的 Python package 生态工程
- 解决 ACP 协议适配、本体验证或 Gemini CLI 集成逻辑
- 迁移所有其他 OpenClaw skill 到统一 venv/runtime model
- 通过修改 system Python 全局环境来作为本 issue 的完成方案

### 2.5 User / Operator Stories
- 作为 `leio-sdlc` 的维护者，我希望开发、测试、部署后 runtime 到底用哪个 Python 环境是明确的，这样我引入新依赖时不会再陷入环境歧义。
- 作为后续 #50 的上游依赖方，我希望在 ACP 验证开始前，Python execution/runtime contract 已经稳定存在，这样后续 PRD 不再被环境问题污染。
- 作为 deploy/CI 维护者，我希望 GitHub CI、开发环境和 skill runtime 使用一致的执行模型，这样“本地可跑、部署不可跑”或“CI 可跑、本地不可跑”的漂移能被压缩。
- 作为多-skill 环境的操作者，我希望 `leio-sdlc` 的 Python environment hardening 不会顺带污染其他 skill 的运行方式。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 issue 采用“四段式 execution/runtime contract 收敛”方案。

### 3.1 Layer 1: Single Source of Truth for Python Dependencies
首先为 `leio-sdlc` 建立唯一、正式的 Python dependency entry，作为项目依赖声明的单一来源。

本 issue 在此明确钉死：
- 唯一正式 Python dependency entry 为仓库根目录下的 `requirements.txt`
- 当前阶段 `requirements.txt` 同时承载 runtime、开发、测试所需依赖
- 当前已在正式测试/CI 路径中使用的 Python 依赖（例如 `pytest`、`PyYAML` 及同类正式依赖）必须一并纳入 `requirements.txt`，不得继续依赖 CI 中额外临时安装形成第二套隐式依赖来源

设计原则：
- 只能存在一个正式 Python dependency entry
- 后续新增 Python 依赖必须写入这一入口
- 不允许为不同执行场景各自发明平行依赖入口
- 依赖入口的存在应足以支撑本地开发、CI 安装、runtime provisioning 三个方向

该层要解决的是“依赖写在哪里”这个问题，而不是“依赖如何分发到更广义安装目标”。

### 3.2 Layer 2: Controlled Development/Test Execution Context
为 repo 本地开发与测试建立受控 execution context。

本 issue 在此明确采用以下策略：
- 开发/测试 execution context 使用仓库根目录下的 `.venv`
- 正式开发/测试命令必须通过显式解释器路径、包装器或脚本入口落到该 `.venv`，而不是依赖人工先 `source .venv/bin/activate`

设计原则：
- 开发/测试命令必须落到受控 Python execution context
- 正式命令路径不得依赖人工先 `source .venv/bin/activate`
- 应优先通过显式解释器路径、包装器、脚本或 make-style 入口约束命令落点
- 该 execution context 主要服务于本地开发、pytest、静态检查、局部验证

该层的核心不是“必须手工 activate”，而是“命令执行落点明确且可重复”。

### 3.3 Layer 3: Controlled Deployed Runtime Execution Context
为部署后的 `leio-sdlc` skill runtime 建立受控 execution context。

本 issue 在此明确采用以下策略：
- runtime execution context 使用独立于开发 `.venv` 的 runtime `.venv`
- 默认落点为已部署 `leio-sdlc` skill 根目录下的 `.venv`
- deploy 后的 skill 脚本必须显式绑定该 runtime `.venv` 的 Python 解释器
- runtime `.venv` 必须在每次新的 staging release 中重建，不复用旧 release 的 runtime `.venv`
- runtime provisioning、import smoke、以及 startup smoke 必须在 staging release 中完成；只有全部通过后才允许 atomic swap 到正式运行位置

设计原则：
- 部署后 skill 脚本必须显式绑定预期 Python 解释器
- 不得默认把 system Python 当作正式 runtime 契约
- deploy 不再只是复制文件，还必须保证最小 runtime provisioning 成立
- runtime execution context 与开发 execution context 必须明确分离，以避免开发环境污染已部署 runtime，并避免运行时隐式依赖工作区路径
- 不得要求其他 skill 被动共享 `leio-sdlc` 的 runtime 环境

该层解决“部署后到底由哪个 Python 来跑 skill 脚本”的问题。

### 3.4 Layer 4: GitHub CI Alignment
使 GitHub CI 与上述 execution contract 一致。

本 issue 在此明确采用以下策略：
- GitHub CI 必须至少完成：建立受控 Python execution context、从 `requirements.txt` 安装依赖、运行标准开发/测试命令、以及执行至少一个最小 execution/runtime contract smoke
- CI 在准备好环境后，必须优先复用与本地一致的正式开发/测试入口（wrapper、脚本入口、或等价统一入口），而不是在 workflow 内重新发明一套与本地分叉的独立命令契约
- 本 issue 不要求 CI 模拟完整 Hub-style 安装/分发路径
- 公开资料可作为 GitHub hosted runner 通常具备 venv 能力的背景参考，但不得替代本 issue 在自身 CI 中保留的最小 execution contract 验证

设计原则：
- CI 必须从正式 dependency entry 安装依赖
- CI 必须显式创建或使用受控 Python execution context，而不是依赖 runner 宿主机偶然状态
- CI 的命令入口应与本地开发/测试模型尽量一致，减少双轨行为
- CI 至少应覆盖 execution contract 的基础验证，而不仅是业务测试

该层解决“CI 是不是在验证同一个世界”的问题。

### 3.5 Canonical Smoke Validation Policy
为避免将真实长任务、副作用任务或实现者自由发挥误当成 smoke，本 issue 在此明确采用以下 smoke policy：
- startup-level smoke validation 必须选择“最小、无副作用、能验证解释器绑定、关键 import 成功以及主启动路径初始化成功”的正式命令路径
- 不得把完整 auditor/orchestrator/长生命周期业务执行作为默认 smoke validation
- 若仓库当前缺少正式 smoke entrypoint，本 issue 允许新增一个最小、明确、无副作用的 smoke 入口作为正式 contract 的组成部分
- deploy 和 CI 中引用的 smoke validation 必须使用同一官方定义，而不是各自发明不同命令

### 3.6 Python Invocation Triage Policy
为避免把本 issue 扩张成“全仓 `python3` 文本清洗”，本 issue 在此明确采用以下分级治理策略：
- contract-critical `python3` 路径必须在本 issue 中修正，至少包括：正式开发/测试入口、deploy/runtime 启动入口、GitHub CI 默认路径、以及与 execution contract 直接相关的 smoke/tests
- 这些 contract-critical 路径若仍保留裸 `python3` 并导致执行落点不受控，应视为本 issue 未完成
- 历史文档、归档 PRD、非默认 mocked/e2e、模板与参考材料中的 `python3` 残留不属于本 issue 阻塞范围，但必须被显式识别为后续清理债务
- 后续清理不得反向扩大本 issue scope；contract-non-critical 清理应通过独立 follow-up issue 处理

### 3.7 Authorized Change Surface
本 issue 默认允许且建议的改动方向包括：
- Python dependency entry 相关文件
- 用于开发/测试命令约束的脚本、包装器或配置
- deploy/runtime 中与 Python execution context 绑定相关的脚本
- GitHub CI workflow 中与 Python 环境建立和命令执行相关的配置
- 与上述 execution contract 直接相关的测试/fixture/smoke validation

未经额外批准，不得在本 issue 内新增与执行契约无关的功能性业务逻辑工程。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 开发环境执行落点明确**
  - **Given** `leio-sdlc` 开发者在本地仓库中执行标准开发/测试命令
  - **When** 这些命令被触发
  - **Then** 它们必须通过受控 Python execution context 执行，而不是依赖当前 shell 恰好激活了某个环境

- **Scenario 2: 依赖声明入口唯一且可用**
  - **Given** 项目需要声明 Python 第三方依赖
  - **When** 维护者为 `leio-sdlc` 增加或更新依赖
  - **Then** 必须存在且只存在一个正式 Python dependency entry 作为合法落点

- **Scenario 3: 部署后 runtime 不依赖 system Python 偶然状态**
  - **Given** `leio-sdlc` skill 已部署到运行位置
  - **When** skill 脚本被触发执行
  - **Then** 它必须通过显式受控的 Python execution context 运行，而不是依赖 system Python 是否偶然已安装所需依赖

- **Scenario 4: Deploy 包含最小 runtime provisioning**
  - **Given** 需要部署更新后的 `leio-sdlc`
  - **When** deploy 流程执行
  - **Then** 除了同步代码文件外，还必须在 staging release 中完成 runtime `.venv` 的创建或校验、从 `requirements.txt` 安装/同步依赖、执行最小 import smoke、并执行至少一次无副作用的 skill 启动级 smoke validation；任一环节失败都必须明确 fail-fast，且不得进行 atomic swap

- **Scenario 5: GitHub CI 与 execution contract 对齐**
  - **Given** GitHub CI 运行 `leio-sdlc` 的测试或检查
  - **When** workflow 启动
  - **Then** CI 必须显式建立/使用受控 Python execution context，从 `requirements.txt` 安装依赖，运行标准开发/测试命令，并执行至少一个最小 execution/runtime contract smoke，而不是依赖 runner 机器偶然状态

- **Scenario 6: 其他 skill 不被隐式污染**
  - **Given** 同一环境中存在多个不同行为模式的 skill
  - **When** `leio-sdlc` 完成 execution/runtime contract hardening
  - **Then** 该变更不得要求其他 skill 自动继承、共享或被动切换到 `leio-sdlc` 的 Python execution context

- **Scenario 7: 本 issue 不承担安装/分发最终模型**
  - **Given** 后续可能存在更广义的安装、打包或 Hub-style 分发需求
  - **When** 本 issue 完成
  - **Then** 本 issue 只需证明本地开发、测试、部署后 runtime、以及 GitHub CI 的 execution contract 已明确，不要求同时解决更广义安装/分发问题

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
本 issue 的核心质量风险不是“某个脚本没跑通”，而是：
- execution contract 仍然依赖人工记忆或机器偶然状态
- 本地、CI、runtime 三套环境看似相似、实际不同
- 依赖新增后再次触发环境争议，导致后续 issue 被污染
- deploy 名义完成但 runtime 实际不可运行

### 5.2 Testing Strategy
#### Required
- 至少一条本地开发/测试命令落点验证路径
- 至少一条 runtime execution path 验证路径
- 至少一条 deploy 后最小 provisioning smoke
- 至少一条 CI execution contract 对齐验证路径
- 至少一条“其他 skill 不被隐式污染”的边界验证思路

#### Mock / Isolation Guidance
- 不需要把真实 ACP/Gemini/远程外部协议引入本 issue 的默认质量门
- 应优先聚焦 Python execution context、解释器绑定、依赖安装落点、deploy/runtime 路径约束
- 对可能依赖真实外部服务的场景，应使用 mock、stub 或最小本地 smoke 替代

#### Regression Strategy
- 对 execution contract 本身建立最小回归保护
- 不要把“手工 source 成功”当成质量门通过标准
- 对 runtime execution path 与 CI path 的关键入口建立回归验证，避免后续依赖增加时再次漂移

### 5.3 Quality Goal
该 issue 的质量目标是：
- 让 `leio-sdlc` 的 Python execution model 变得明确、可重复、可部署、可在 CI 中重演
- 为后续引入 Python 依赖的功能性 issue（如 #50）提供稳定地基
- 同时保持 scope 有界，不把问题膨胀成完整安装/分发工程

## 6. Framework Modifications (框架防篡改声明)
本 PRD 授权修改以下类别的文件（具体路径由实施时按实际最小改动确定）：
- 项目既有或新建的唯一 Python dependency entry 相关文件
- `leio-sdlc` 中与开发/测试命令入口相关的脚本、包装器或配置
- `leio-sdlc` 中与 deploy/runtime Python 解释器绑定相关的脚本
- GitHub CI workflow 中与 Python 环境建立、依赖安装、命令执行相关的配置
- 与上述 execution/runtime contract 直接相关的测试、fixture、smoke validation 支撑文件

本 PRD **不授权** 在本 issue 中进行以下类别的大范围改造：
- ACP/Gemini/外部协议接入逻辑本体实现
- 最终 ClawHub / Hub-style 安装与分发契约落地
- 将所有其他 skill 统一迁移到同一 Python runtime 模式
- 通过修改 system Python 全局包状态作为正式交付方案
- 与 execution/runtime contract 无关的功能性产品逻辑开发

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将问题从“某个依赖装不上”提升为“`leio-sdlc` 缺少正式 Python execution/runtime contract”，并将 scope 收敛到本地开发、测试、部署后 runtime 与 GitHub CI。
- **v1.1**: 明确安装/分发/ClawHub 兼容性属于独立 follow-up 轨道，不作为本 issue 的完成条件，从而避免 scope 膨胀为完整 packaging/distribution 工程。
- **v1.2**: 钉死唯一依赖入口为根目录 `requirements.txt`，明确开发 execution context 使用 repo `.venv`，runtime execution context 使用已部署 skill 根目录下的独立 `.venv`，并收紧 deploy/CI 的最小完成定义与 coder/环境侧职责边界。
- **v1.3**: 补充 requirements.txt 选型 rationale、开发/运行 venv 分离 rationale、手工前置不等于交付本身的边界，以及“搜索结论不能替代最小 CI execution contract 验证”的原则说明。
- **v1.4**: 结合 coder-readiness 检查结果，钉死 runtime provisioning 必须在 staging release 中完成、runtime `.venv` 每次 release 重建、`requirements.txt` 当前阶段同时承载 runtime/dev/test 依赖，以及 startup smoke 必须使用统一的无副作用官方入口。
- **v1.5**: 明确将仓库内 `python3` 调用分级治理：正式 execution contract 路径属于本 issue 必修范围，历史文档/归档/非默认 mocked/e2e 等残留改为后续独立清理债务。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`required_python_dependency_entry`**:
```text
requirements.txt at the repository root, currently serving runtime, development, and test dependencies together
```

- **`required_dev_execution_context`**:
```text
repository-root .venv
```

- **`required_runtime_execution_context`**:
```text
deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap
```

- **`required_project_scope`**:
```text
leio-sdlc local development, testing, deployed runtime execution, and GitHub CI only
```

- **`required_contract_critical_python_surfaces`**:
```text
formal development/test entrypoints, deploy/runtime launch paths, GitHub CI default paths, and execution-contract-related smoke/tests
```

- **`followup_cleanup_issue_for_noncritical_python3_refs`**:
```text
Issue #59
```

- **`required_smoke_validation_policy`**:
```text
Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation.
```

- **`required_current_official_docs_to_update`**:
```text
Update current effective development/runtime entry documentation and prompts (including active SKILL.md, hooks, JIT prompts, README or equivalent official entry docs) to match the new execution contract; archived/history-only docs are not blocking for this issue.
```

- **`forbidden_distribution_scope_in_this_issue`**:
```text
ClawHub installation, public packaging/distribution contract, and cross-skill global runtime unification
```

- **`runtime_contract_core_goal`**:
```text
Define a controlled, repeatable Python execution contract for local development, testing, deployed skill runtime, and GitHub CI without depending on unmanaged system Python state.
```
