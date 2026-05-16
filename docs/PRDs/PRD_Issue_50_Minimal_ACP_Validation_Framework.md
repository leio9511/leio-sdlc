---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 50 Minimal ACP Validation Framework

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 目前对外部引擎/CLI 的集成主要建立在 direct CLI launch 路径上。该模式在短期内可工作，但带来几个核心问题：

1. 不同 CLI 的接入边界不统一，导致 runtime 语义、continuity 能力、失败退化策略难以用统一控制面语言表达。
2. Issue #49 已经定义了 runtime contract v1 的基础文档、schema、类型与样例，但这些 contract 仍然是工作假说，尚未经过真实 ACP 路径验证。
3. 目前无法系统性回答“某个 CLI 是否可以通过 ACP 接入，而不是只能通过 direct CLI launch 接入”。
4. 如果没有一个最小 ACP 验证框架，后续 #51（registry/config）与 #52（routing/orchestrator）会建立在未经验证的假设上，风险较高。

本 PRD 的目的不是直接推动全量 ACP 迁移，也不是替换现有 direct CLI 路径，而是建立一个最小、可重复、可审计的 ACP 验证框架，使 `leio-sdlc` 可以对单个 CLI 做出有证据的 ACP 可接入性判断。

本 PRD 采用一个明确前提：
- 默认假定目标 CLI / ACP endpoint 已经自行完成 auth。
- `leio-sdlc` 在本阶段不负责集中 auth 管理、token 注入、corp SSO 或 delegated auth。
- 只有在试验明确证明 self-authenticated CLI/ACP endpoint 不可行时，才考虑把 auth 管理纳入后续 issue。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. 系统必须提供一个最小 ACP adapter / client baseline，用于连接一个已自认证的 ACP endpoint。
2. 系统必须能够通过该 baseline 完成一次最小请求/响应回路。
3. 系统必须能够在目标 ACP 端提供相关能力时捕获 session / continuation handle。
4. 系统必须能够尝试至少一次受限的 continuation / resume 路径。
5. 系统必须能够结构化记录验证观察结果，并映射回 Issue #49 的 contract 关键字段，至少包括：
   - `continuity_mode`
   - `handle_acquisition_strategy`
   - `resume_requires_same_runtime_state`
   - `fallback_policy`
   - 初步 `capability_surface` 判断
6. 系统必须能够对至少一个目标 CLI 给出明确的 ACP viability verdict，结论类型至少包括：
   - Supported
   - Partially Supported
   - Not Suitable at This Stage
7. 系统必须提供可重复执行的 smoke tests，用于验证 baseline 行为与 failure-path 行为。
8. 系统必须保证新增测试与 preflight/CI 设计不会通过“故意测试变红”来表达否定性验证结论；负面 verdict 必须通过结构化产物表达，而不是通过破坏默认测试绿灯表达。
9. 系统必须使用 Python 实现最小 ACP baseline，并优先使用官方 Python MCP SDK（PyPI 包名 `mcp`）。
10. 系统必须把 Python MCP SDK 作为项目依赖显式声明到仓库，而不能仅依赖机器当前环境。
11. 系统必须假定 SDK 已由环境预装可用；本 issue 不负责首次机器级安装流程设计，但实现仍必须把依赖声明补入项目。
12. 系统必须提供最小、固定的运行时能力边界，至少包含以下六个操作能力：
   - `connect`
   - `execute_turn`
   - `capture_handle`
   - `resume_once`
   - `classify_failure`
   - `emit_verdict`

### 2.2 Non-Functional Requirements
1. 该实现必须优先复用标准协议 SDK，不得从头自研协议层。
2. 该实现必须保持 scope 有界，不得在本 issue 中演化为全量多 CLI 迁移工程。
3. 该实现必须与现有 direct CLI 路径并存，禁止在本 issue 中删除 legacy runtime path。
4. 该实现必须保持与 corp 环境兼容的设计方向，即默认不依赖 `acpx` 作为唯一核心依赖。
5. 该实现必须把“否定性的 ACP 适配结论”视为合法输出，而不是默认把“被测 CLI 不适合 ACP”视为项目失败。
6. 该实现必须区分“验证框架实现成功”与“被测 CLI verdict 为否定”这两类结果，前者通过 SDLC 质量门，后者通过结构化结果表达，不得通过测试失败表达。
7. 本 issue 默认禁止引入 NodeJS 作为并行实现栈；只有在 Python 官方 SDK 路线被明确验证为无法满足最小 client/continuation 需求后，才允许通过后续决策单独讨论第二技术栈。
8. 本 issue 不要求 coder 负责机器级环境设置；环境侧可以预装 SDK，但代码交付必须在仓库内声明依赖、体现缺失时的清晰失败面，并保持 fresh checkout 可重建。

### 2.3 Explicit Non-Goals
本 PRD 不包含以下目标：
- 多引擎完整 ACP 支持
- config-driven engine registry 落地（后续 #51）
- agent_driver / orchestrator 的 ACP-aware routing 完整接入（后续 #52）
- corp redaction / governance / onboarding hardening（后续 #53）
- 集中 auth、corp SSO、delegated token flow
- coder-grade workflow 正式支持
- 把单一 CLI 的 ACP 成功错误外推为对所有 CLI 的证明

### 2.4 User / Operator Stories
- 作为 `leio-sdlc` 的架构维护者，我希望有一个最小 ACP 验证框架，以便我能判断某个 CLI 是否值得通过 ACP 接入，而不是只能靠 direct CLI launch。
- 作为后续 registry / routing 设计者，我希望 #50 能提供基于真实试验的结构化结论，而不是只提供抽象假设，以便后续 issue 的设计建立在证据之上。
- 作为 corp/private CLI 未来接入者，我希望系统默认允许 CLI 自己处理 auth，而不是要求 SDLC 先接管认证系统，以降低第一阶段接入成本。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 issue 采用“三层式最小 ACP 验证框架”方案。

### 3.1 Layer 1: Minimal ACP Adapter Baseline
实现一个最小的 SDK-based ACP client/adapter layer，职责如下：
- 连接目标 ACP endpoint
- 发起最小 prompt/task 请求
- 接收响应
- 捕获 continuation/session handle（若协议端提供）
- 执行一次受限 resume 尝试
- 结构化报告成功、失败与退化观察

设计原则：
- 优先使用官方 Python MCP SDK（PyPI 包名 `mcp`）
- 使用 Python 实现，不引入 NodeJS 并行实现栈
- 不从头实现协议层
- 不以 `acpx` 为唯一正式依赖；`acpx` 只能作为参考或开发阶段辅助，不得成为 corp 兼容性的单点前提
- 保持 adapter 层薄，不在本 issue 内构建完整 runtime manager
- 首次机器级 SDK 预装不属于 coder 职责，但项目依赖声明属于 coder 职责

默认文件落点必须如下：
- 运行时实现放在 `scripts/` 下
- 自动化测试放在 `tests/` 下
- 测试夹具与结构化样例放在 `tests/fixtures/` 下（若需要新增）

本 issue 默认允许且建议的新增文件为：
- `scripts/acp_client.py`
- `scripts/acp_probe.py`
- `scripts/acp_smoke.py`
- `tests/test_acp_client.py`
- `tests/test_acp_probe.py`

未经额外批准，不得新增独立 Node 子项目目录、独立前端/sidecar 子仓结构，或与本 issue 无关的第二运行时工程。

### 3.2 Layer 2: Contract-Aware Probe Layer
在 adapter 层之上实现 contract probe 逻辑，用于将真实运行观察映射回 #49 的 runtime contract baseline。

重点验证：
- ACP lane 是否真实存在并可重复进入
- continuation 更接近 `authoritative_resume`、`mapped_resume` 还是更弱语义
- handle 获取是 protocol-native、returned handle、还是需要本地映射补足
- continuation 是否依赖 same runtime state
- fallback 是 fail-closed、fallback-to-legacy、还是其它模式
- capability surface 是 runtime-managed、client-mediated 还是 mixed

该层的主要目标不是“证明 ACP 可用”，而是“把 ACP 的真实行为翻译成 `leio-sdlc` 可以做控制面决策的语言”。

该层对外能力边界必须稳定映射到以下最小接口语义：
- `connect`: 连接目标 ACP endpoint
- `execute_turn`: 执行一次最小请求/响应回路
- `capture_handle`: 获取 continuation/session handle 或明确返回不可用
- `resume_once`: 基于已知 handle 执行一次受限 continuation
- `classify_failure`: 把失败映射成 contract-relevant 类别
- `emit_verdict`: 输出最终 structured verdict

允许内部实现自由，但不得扩大为通用 runtime framework 或额外设计大而全抽象层。

### 3.3 Layer 3: Validation Harness
验证 harness 分两类：

#### A. Baseline / Contract Smoke
用于验证最小 ACP lane 是否存在，并测试 contract v1 的核心假设，至少包括：
- connect smoke
- minimal request/response smoke
- handle capture smoke
- one-step continuation/resume smoke
- failure-path observation smoke

这些 smoke 必须设计为：
- 在受控前提下可稳定通过 preflight / CI
- 验证框架行为与结构化输出是否正确
- 不把“被测 CLI 最终 verdict 为否定”编码为 failing test

#### B. Exploratory Complex Smoke
用于探索更复杂场景（例如 coder-like task）是否暴露出额外 gap，目标是识别限制，而不是要求正式支持。可能包含：
- 长上下文任务
- 初步文件/工具/终端相关交互探测
- 更长的连续性链路
- 对 side effects 风险的观察

这些探索性验证可以产出 yellow/red 结论，但不得以破坏默认 preflight/CI 绿灯为代价。必要时应采用非阻塞、显式标注或结构化报告方式表达结果。

### 3.4 Why This Design
该设计的核心取舍：
- 优先构建“验证框架”而非“直接交付生产级 ACP integration”
- 把 #50 视为 evidence-building stage，而不是 migration stage
- 允许验证输出为 green / yellow / red 三类 verdict
- 避免把 #50 与 #51 / #52 / #53 的后续工作混成一体

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 基础 ACP lane 可执行**
  - **Given** 一个已自认证的目标 CLI / ACP endpoint 可在本地或受控环境中被访问
  - **When** `leio-sdlc` 通过最小 ACP adapter 发起一次最小请求
  - **Then** 系统必须能够明确地得到成功或失败结果，并以结构化方式记录下来

- **Scenario 2: 最小请求/响应回路成立**
  - **Given** 基础 ACP lane 已建立
  - **When** 系统执行一次最小 request/response turn
  - **Then** 系统必须能够观测到可解释的响应结果，而不是仅有无法分类的原始过程日志

- **Scenario 3: Continuation / handle 行为被验证**
  - **Given** 目标 ACP endpoint 提供或看似提供 session / continuation 能力
  - **When** 系统尝试捕获 handle 并执行一次受限 continuation / resume
  - **Then** 系统必须能够明确记录 continuation 是否成立、是否依赖 same runtime state，以及 handle 获取方式的初步判断

- **Scenario 4: Failure-path 观察是合法结果且不破坏 CI**
  - **Given** 目标 ACP path 在 continuation 或能力面上出现失败、不可用或退化
  - **When** 系统运行 failure-path smoke 或探索性验证
  - **Then** 该 issue 不应仅因为目标 CLI 未绿灯通过而被判失败；同时该负面结论必须通过结构化结果、显式 verdict 或非阻塞验证产物表达，而不得通过让默认测试或 preflight 变红来表达

- **Scenario 5: 输出 ACP viability verdict**
  - **Given** 至少一条真实 ACP 验证路径已经执行
  - **When** 验证流程完成
  - **Then** 系统必须给出明确 verdict，至少属于 Supported / Partially Supported / Not Suitable at This Stage 之一

- **Scenario 6: Legacy path 不被提前替换**
  - **Given** 现有 direct CLI runtime path 仍然承担生产可用职责
  - **When** 本 issue 的 ACP 验证框架引入仓库
  - **Then** 系统不得删除或隐式替换现有 legacy direct CLI path

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
本 issue 的核心质量风险不是“功能没跑通”，而是：
- 没有做出真正可复用的验证框架
- 把单次演示成功误当成长期接入结论
- 把被测 CLI 的否定 verdict 错误地编码成 failing tests
- 让探索性验证破坏 preflight / CI 绿灯
- 没有输出足以指导后续 issue 的结构化证据

### 5.2 Testing Strategy
#### Required
- 至少一条 baseline contract smoke path
- 至少一条 continuation/handle 验证路径
- 至少一条 failure-path 观察路径
- 至少一次结构化 verdict 输出
- 所有纳入默认质量门的 automated tests 与 preflight 检查必须保持可绿

#### Exploratory
- coder-like task smoke
- 更复杂的 capability surface 探测
- 初步 side-effect 风险暴露

#### Regression Strategy
- 仅对已证明存在且可稳定表达的基础能力编写回归保护
- 不要把未经证实的能力假设固化为必须全绿的自动化测试
- 若 exploratory smoke 暴露出已知不稳定能力，应记录为 structured finding / expected limitation / explicit verdict，而不是让默认测试红掉
- 否定性技术结论必须通过结果产物表达，不得通过破坏 CI 表达

### 5.3 Quality Goal
该 issue 的质量目标是：
- 提供一个可信的 ACP validation harness
- 让后续 issue 可以基于证据推进
- 确保“否定性的验证结论是有效结果”这一原则被保留
- 同时确保该原则不会通过破坏 preflight / CI 绿灯来表达

## 6. Framework Modifications (框架防篡改声明)
本 PRD 授权修改以下类别的文件（具体路径由实施时按实际最小改动确定）：
- `leio-sdlc` 仓库中用于 runtime / adapter / client baseline 的新增或局部扩展模块
- 与该最小 ACP 验证框架直接相关的 smoke test / test fixture / structured observation 支撑代码

本 PRD **不授权** 在本 issue 中进行以下类别的大范围改造：
- 全局 engine registry 落地性改造（留给 #51）
- 主 driver / orchestrator 的全面 ACP routing 集成（留给 #52）
- corp auth / SSO / secret propagation 体系改造
- 对现有 legacy direct CLI path 的移除或大规模替换
- 新增 NodeJS 并行技术栈或独立 sidecar 子工程
- 把 SDK 仅作为机器局部状态使用而不进入仓库依赖声明

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 #50 定义为“最小 ACP 验证框架”而非“完整 ACP 集成工程”；默认假定 CLI / ACP endpoint 自行完成 auth；把验收标准从“green path 必须成功”修正为“框架必须能产出结构化 verdict”。
- **v1.1**: 明确“被测 CLI 的否定 verdict 是合法结果”不等于“允许默认测试或 preflight 变红”；负面结论必须通过结构化产物、非阻塞验证或显式报告表达，CI 绿灯必须保持。
- **v1.2**: 钉死 Python-first 技术路线、官方 Python MCP SDK 优先、默认文件落点、最小接口语义，以及“环境可预装但项目依赖声明必须进入仓库”的执行边界，防止 coder 在技术栈、目录结构、依赖接入方式上自由发挥。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`python_sdk_package_name`**:
```text
mcp
```

- **`required_runtime_language`**:
```text
Python
```

- **`forbidden_parallel_stack_without_explicit_followup_decision`**:
```text
NodeJS
```

- **`required_default_new_files`**:
```text
scripts/acp_client.py
scripts/acp_probe.py
scripts/acp_smoke.py
tests/test_acp_client.py
tests/test_acp_probe.py
```
