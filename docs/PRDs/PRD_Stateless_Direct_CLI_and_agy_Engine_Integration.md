---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Stateless_Direct_CLI_and_agy_Engine_Integration

## 1. Context & Problem (业务背景与核心痛点)

`leio-sdlc` 目前支持两种执行引擎:`openclaw_native` 和 `gemini_direct_cli`。需要新增 `agy`(Antigravity CLI)作为第三个可用的执行引擎。

当前有三个结构性问题阻塞了这个目标:

### Problem 1: agent_driver.py 靠 provider-specific branching 选择引擎
`scripts/agent_driver.py` 通过环境变量 `LLM_DRIVER` 硬编码了 `gemini` 和 `openclaw` 两个分支。每新增一个 CLI 都需要新增 `if/elif` 分支,这直接违反了仓库已在 #49/#51/#52 及 `PRD_Config_Driven_Multi_CLI_Engine_Integration.md` 中确立的 config-driven 方向。

### Problem 2: Direct CLI 引擎的连续性语义不可工程信任
- Gemini CLI 的 "resume" 依赖 `--list-sessions` + session-set diffing 的启发式发现,不是 protocol-native authoritative handle。
- 开源项目 `openab/agy-acp` 展示的 agy conversation handle discovery 同样依赖 `~/.gemini/antigravity-cli/conversations/*.pb` 的文件修改时间扫描,不具备合约稳定性。
- 当前 `engine_registry.py` 允许的 `continuity_mode` 枚举包含了中间地带值(`authoritative_resume`、`unsupported`),但实际只存在两类引擎:有权威原生 handle 的,和没有的。

### Problem 3: 已有 config-driven 基础设施,但生产代码未完成迁移
- `scripts/engine_registry.py`、`config/engines.default.json`、`docs/Issues/ISSUE-49_Runtime_Contract_v1_ADR.md` 已经定义了 registry/contract 骨架。
- `docs/PRDs/PRD_Config_Driven_Multi_CLI_Engine_Integration.md` 明确了 generic external CLI contract 的方向。
- 但 `agent_driver.py` 仍然在 `LLM_DRIVER=gemini` 的分支逻辑下运行,Gemini 未被迁移到 generic renderer。

### Problem 4: Stateless 重试机制已经可行,只需微调
- Coder 的 JIT retry 上下文(PR 文件、PRD、feedback-file、system-alert)全部通过文件系统和命令行参数传递,会话记忆不是必要依赖。
- Reviewer 的 JIT retry 是唯一真正依赖会话续接的路径(`--system-alert` 发到 `.reviewer_session` 记录的同一 session),但可以通过重装 full prompt + alert 的方式改为 stateless。
- Planner、Verifier、Auditor、Arbitrator 已经是一过式 / stateless 调用。

### Problem 5: 双环境运行时需求
- OpenClaw 环境:`openclaw_native` 有权威 session handle(`sessions_spawn` 返回),已经生产验证,应保持 stateful。
- Corp 环境:不能依赖 OpenClaw runtime,必须通过 `agy` 或未来其他 CLI 作为 direct CLI engine 执行。

## 2. Requirements & User Stories (需求定义)

### FR-1: 简化连续性合约为两种模式
将 engine contract 中的 `continuity_mode` 从当前多值简化为 `stateful` 和 `stateless` 两种。

判定标准:
- **stateful**:runtime 原生(非 heuristics、非 post-hoc discovery、非文件系统扫描)返回一个稳定、可跨进程复用的 handle,且此行为有官方合约保证。
- **stateless**:所有其他情况。包括通过 session listing diff、conversation 目录扫描、或任何启发式手段获取 handle 的引擎。

**当前引擎分类**:
- `openclaw_native` → `stateful`
- `gemini_direct_cli` → `stateless`
- `agy_direct_cli` → `stateless`
- 所有未来 direct CLI 引擎 → 默认 `stateless`

### FR-2: 通用 direct CLI renderer
从 `agent_driver.py` 中提取现有的 Gemini one-shot 路径，抽象为通用的 `invoke_direct_cli(engine_spec, task_string, ...)` 渲染器。

渲染器必须从 engine spec 中读取以下可配置字段，不硬编码任何 CLI 名：
- `cli_alias`
- `execution.executable`
- `execution.one_shot_args`：单次调用的参数模板（如 `-p`, `--print`, `{prompt}`）
- `execution.model_arg`：模型参数模板
- `execution.workspace_arg`：工作目录注入参数（如 `--add-dir`）
- `execution.permission_args`：权限相关参数（如 `--dangerously-skip-permissions`）
- `execution.sandbox_args`：沙盒参数
- `execution.timeout_seconds`：超时
- `execution.env_extra`：环境变量注入

本 PRD 中 `execution` subsection 使用 `env_extra` 作为唯一字段名。不得再使用 `env_template`、`env_vars`、`extra_env` 等同义替代字段。

### FR-3: agy 作为 direct_cli engine 接入
通过 engine config 注册 `agy_direct_cli`,不新增 provider-specific 代码分支。

`agy` 的 one-shot 调用形式为:
```
agy --add-dir <workspace> --print <prompt>
```

可选参数(由 local overlay 控制):
- `--dangerously-skip-permissions`
- `--sandbox`
- `--print-timeout`

### FR-4: Gemini 迁移到 generic renderer
Gemini direct CLI 使用与 agy 相同的 generic renderer 路径。迁移后 Gemini 相关测试必须保持通过。

本 PRD 不允许在 `agent_driver.py` 中长期保留活跃的 Gemini provider-specific 执行分支作为运行时回退路径。若需要回滚，只能通过配置级切换（如 engine entry swap、禁用 direct_cli entry、恢复已知稳定 release），不能通过在主执行路径中保留永久性的 legacy Gemini 分支实现。

### FR-5: Stateless 重试硬化
- Coder retry(yellow path):每次重试为全新 one-shot 调用。retry prompt 需包含上一轮 agent stdout。
- Reviewer retry(JSON 解析失败):改为完整 re-prompt(包含 PRD + PR file + diff + alert),不再依赖 `.reviewer_session` 发送 system alert。
- 所有 direct CLI engine 的重试不产生 `.coder_session`、`.reviewer_session`、`session_map_file`。

### FR-6: OpenClaw native 不改变
`openclaw_native` 保持现有会话语义和行为，不做任何 stateful/stateless 转换。

本 PRD 不要求在 OpenClaw engine entry 上完成 `handle_acquisition_strategy` 等字段的语义归一化。OpenClaw entry 视为既有基线，仅要求 direct_cli 路径完成本 PRD 变更。

### FR-7: 合约修订
更新以下文件中的 `continuity_mode` 枚举:
- `scripts/engine_registry.py`
- `config/engines.default.json`
- `docs/Issues/ISSUE-49_Runtime_Contract_v1_ADR.md`

允许值从当前多值缩减为 `stateful | stateless`。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 设计决策记录

| 决策 | 内容 | 依据 |
|------|------|------|
| D1 | Hybrid 连续性模型:openclaw=stateful,direct_cli=stateless | openclaw 有权威 handle;所有 direct CLI 的 resume 都依赖不可信任的 heuristics |
| D2 | 合约简化:continuity_mode 降至 2 个值 | `mapped_resume`/`degraded_resume` 鼓励将 heuristics 误当连续性,应从 contract 中删除 |
| D3 | Generic external CLI renderer | 消除 `agent_driver.py` 中的 provider-specific 分支,对齐 config-driven 方向 |
| D4 | agy 作为 direct CLI | 不通过 ACP(acpx 无内置 agy 支持),不通过 SDK(先审计 CLI 行为再做决策) |
| D5 | Stateless 重试 = fresh one-shot + full context | 所有 JIT 上下文已通过文件系统/参数传递,会话记忆非必要 |
| D6 | 不碰 ACP | ACP 线保留为研究/审计分支,不阻塞 direct CLI 主线 |
| D7 | Engine 命名:用户面短名 → 内部 engine_id 映射 | `--engine agy` 映射到 `agy_direct_cli`,映射通过 `cli_alias` 字段 |
| D8 | Execution 字段放在 config 层 | `executable`/`one_shot_args` 等不进 `engine_registry.py` 公开 schema |
| D9 | 不碰 OpenClaw 的 handle 字段 | `openclaw_native` 保持 `handle_acquisition_strategy: "unavailable"` |
| D10 | Coder retry stdout 来源 = `AgentResult.stdout` | 内存传递,不落地文件 |
| D11 | Reviewer retry 由 Orchestrator 控制 | `spawn_reviewer.py` 不感知重试;移除 `.reviewer_session` |
| D12 | Session 文件按引擎条件清理 | stateful 保留、stateless 不创建/不依赖/不清理 |

### 3.2 运行时形态

Iteration 1 标准化为两种运行时路径:
1. **`builtin_openclaw`**:`agent_driver.py` 中的内建渲染器,保留一等 OpenClaw-native 执行。
2. **`generic_direct_cli`**:由 engine spec 字段驱动的通用渲染器,用于 Gemini、agy 及所有未来 direct CLI。

不变量:控制面(orchestrator)不应关心解析出的引擎是 OpenClaw、Gemini 还是 agy;它只应关心已校验的引擎能力和标准化的 start/retry 合约。

### 3.3 配置分层

三层模型(沿用现有设计,不变):
1. **Public core schema**:`config/engines.default.json` 中的 engine contract
2. **Public example layer**:OpenClaw、Gemini、agy 作为 conformance samples
3. **Local runtime overlay**:`config/engines.local.json`,用于 corp/private engine 的 command/path/args

### 3.4 核心抽象:Logical Session vs Native Handle(仅 stateful 引擎)

- **logical session key**:SDLC 所有,跨 role workflow 稳定
- **native handle**:provider CLI/runtime 所有,用于续接真实底层会话

Stateless 引擎不参与 handle mapping--每次调用是独立的一次性行为。

### 3.5 目标文件改动清单

| 文件 | 改动性质 | 说明 |
|------|----------|------|
| `scripts/agent_driver.py` | 重构 | 提取 generic direct CLI renderer;消除 `LLM_DRIVER=gemini` 特殊分支 |
| `scripts/engine_registry.py` | 合约修订 | `continuity_mode` 枚举缩减;新增 `stateful`/`stateless` |
| `config/engines.default.json` | 合约修订 | 更新 Gemini entry;新增 agy entry(或占位说明) |
| `config/engines.local.json` | 新增内容 | agy 的 command/path/args 本地覆盖(如放 public 则不修改此处) |
| `docs/Issues/ISSUE-49_Runtime_Contract_v1_ADR.md` | 合约修订 | continuity_mode 字段语义更新 |
| `scripts/orchestrator.py` | 微调 | `--engine` flag choices 支持 agy;direct CLI retry 路径适配 stateless |
| `scripts/spawn_coder.py` | 微调 | stateless retry 时注入上一轮 stdout |
| `scripts/spawn_reviewer.py` | 微调 | 移除 `.reviewer_session` 依赖;system-alert 改为 full re-prompt |
| `scripts/envelope_assembler.py` | 微调 | stateless retry 模式的 prompt assembly 支持 |
| 测试文件 | 新增/更新 | generic renderer 参数化测试;agy engine spec 校验;stateless retry 验证 |

### 3.6 Rollback & Isolation Strategy (回滚与隔离策略)

本 PRD 改动触及 `agent_driver.py` 的核心执行路径和多个 `spawn_*.py` 的 retry 逻辑。必须在实施中保持以下隔离保证。

**隔离原则：改动仅影响 `direct_cli` engine 类。`openclaw_native` 路径零改动。**

**回滚机制：**

1. **OpenClaw native 路径零改动保证**：`invoke_agent()` 中 `openclaw_native` 分支保持全部现有代码路径。新增的 `direct_cli` 分支在 `if runtime_mode == "direct_cli"` 内，不进入 OpenClaw 分支。即使 generic renderer 完全失败，`LLM_DRIVER=openclaw` 的执行路径不受任何影响。

2. **Gemini 回滚为配置级回滚，不是代码分支回滚**：不得在 `agent_driver.py` 中保留长期活跃的 provider-specific Gemini 执行分支作为运行时 fallback。若 generic renderer 在 Gemini 上表现异常，回滚只能通过以下方式之一实现：
   - 恢复到 generic renderer 变更之前的已知稳定 release / commit
   - 在 config 中禁用 `gemini_direct_cli` entry
   - 在 config 中将默认 engine 切回 `openclaw_native`
   - 通过 engine entry swap 恢复到上一个已知稳定的 Gemini direct_cli config

3. **Config overlay 可撤消**：`engines.local.json` 中的 direct_cli engine entries 可通过删除或覆盖回退，不要求改动 public 源码。任何 corp/private execution details 只能通过 overlay 引入或移除。

4. **Session 文件语义严格按引擎类型隔离**：
   - Coder: `teardown_coder_session()` 加 `engine_mode` 参数；仅在 `stateful` 引擎时操作 `.coder_session`。
   - Reviewer: `.reviewer_session` 仅在 `stateful` 引擎下写文件；stateless reviewer retry 通过 orchestrator 全新调用，不依赖 session 文件。
   - `agent_driver.py` 的 `session_map_file` 仅在 `stateful` 引擎下写。

**验证点（合并前必须通过的回归检查）：**
- `LLM_DRIVER=openclaw` 下完整 SDLC 流程执行成功（现有测试全部通过）。
- `LLM_DRIVER=gemini` 下 generic renderer 行为等同于迁移前的黑盒行为（现有 Gemini 测试全部通过）。
- 禁用 `gemini_direct_cli` entry 后系统不会意外落回 provider-specific Gemini 分支，而是按配置 fail-closed 或切回明确的默认 engine。

### 3.7 不可变部分

- OpenClaw native 执行路径不变
- Orchestrator FSM 逻辑不变
- PRD 处理逻辑不变
- `spawn_planner.py`、`spawn_auditor.py`、`spawn_verifier.py`、`spawn_arbitrator.py` 的 prompt 模板不变(除 stateless retry 适配外)
- ACP 相关代码不删除(保留为研究分支)
- `envelope_assembler.py` 的核心 prompt 结构不变

### 3.7 Coder-Readiness Clarifications (2026-05-27 审查决议)

以下 6 项澄清来自 coder-readiness check 对 PRD 与仓库代码的交叉审查。每一项均已回答并作为实施指引纳入本 PRD。

**Q1: Engine 选择器的命名映射**

现状:`--engine choices=["openclaw", "gemini"]` 在多处硬编码。

决议:保持短名作为用户面 CLI flag 标识,内部映射到 registry engine_id:
```
--engine openclaw → engine_id="openclaw_native"
--engine gemini   → engine_id="gemini_direct_cli"
--engine agy      → engine_id="agy_direct_cli"
```
映射逻辑放在 engine spec 中(新增 `cli_alias` 字段),不在 `spawn_*.py` 中散落硬编码。`--engine` choices 从 engine registry 动态读取而非硬编码列表。

**Q2: FR-2 execution 字段的存放位置**

决议:`executable`、`one_shot_args`、`model_arg`、`workspace_arg`、`permission_args`、`sandbox_args`、`timeout_seconds`、`env_template` 这些字段**属于 engine spec 的 execution subsection,放在 config 层(`engines.default.json` 或 `engines.local.json`),不进 `engine_registry.py` 的公开 schema 校验**。

- `engine_registry.py` 继续只校验公开合约字段(`continuity_mode`、`runtime_mode` 等)
- Local overlay 承载 private execution details
- Generic renderer 从合并后的 registry entry 中读取 execution 字段,reader 自己做 basic sanity check

**Q3: OpenClaw `handle_acquisition_strategy`**

决议:本 PRD **不碰** OpenClaw 的 engine entry。`openclaw_native` 保持 `handle_acquisition_strategy: "unavailable"`--该字段对 stateful 引擎的语义留到 #49 后续修订单独处理,不在本次 scope 内。

**Q4: Coder stateless retry 的 "前一 stdout" 来源**

决议:来源为 `invoke_agent()` 返回值 `AgentResult.stdout`。实现方式:

```
previous_stdout = agent_result.stdout
retry_prompt = original_prompt
  + "\n\n## 上一轮输出\n" + previous_stdout
  + "\n\n" + system_alert
```

不需要额外文件路径或持久化。`envelope_assembler.py` 新增 `previous_output` 合约字段,在 retry mode 下由 orchestrator 注入。

**Q5: Reviewer stateless retry 的实现方式**

决议:**不在 `spawn_reviewer.py` 内部增加 retry mode**。做法:

1. Orchestrator 检测 reviewer JSON 解析失败
2. Orchestrator 构造完整 reviewer prompt(与首次调用相同)+ inline alert:`"SYSTEM ALERT: 上轮输出非合法 JSON。请按 schema 重新输出。上轮原文:\n{previous_output}"`
3. 全新调用 `spawn_reviewer.py`(不带 `--system-alert`,带完整 `--prd-file`/`--pr-file`/`--diff-target`)
4. 移除 `.reviewer_session` 的读/写依赖

Orchestrator 控制重试,`spawn_reviewer.py` 不感知重试状态。

**Q6: Session 文件清除范围**

决议:引擎条件判断,不是全仓库消除。

- `openclaw_native` → `.coder_session`、`.reviewer_session`、`session_map_file` **保留**
- 所有 `direct_cli` 引擎 → **不创建、不依赖、不清理(因为不存在)**
- Orchestrator 的 `teardown_coder_session()` 和 blast radius control 加 engine mode 判断:仅在 `stateful` 引擎下操作 session 文件
- `agent_driver.py` 的 `invoke_agent()` 对 `direct_cli` 引擎不写 `session_map_file`

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### Scenario 1: agy 作为 engine 执行 planner
- **Given** agy CLI 已安装在宿主环境,且 `LLM_DRIVER=agy`(或 config 指定 agy engine)
- **When** Orchestrator 启动 planner 角色
- **Then** planner 通过 `agy --add-dir <workspace> --print <prompt>` 执行,返回结构化 PR contract,不产生 `.coder_session` / `session_map_file` / `.reviewer_session`

### Scenario 2: agy 作为 engine 执行 coder
- **Given** agy 被选为 engine,且存在一个 open PR
- **When** Orchestrator 启动 coder
- **Then** coder 通过 agy one-shot 调用执行,产生代码变更;若无变更,orchestrator 检测并进入 yellow path retry

### Scenario 3: Coder stateless yellow path retry(reviewer 拒绝)
- **Given** coder 执行完成,reviewer 返回 ACTION_REQUIRED
- **When** Orchestrator 重试 coder
- **Then** 重试为全新 `agy --print` 调用(非同一 session 续接),prompt 包含上一轮 coder stdout + review 反馈 + PR contract,产生修复后的代码

### Scenario 4: Reviewer stateless retry(JSON 解析失败)
- **Given** reviewer 输出的 JSON 无法解析
- **When** Orchestrator 重试 reviewer
- **Then** 重试为全新完整 prompt 组装(包含 PRD + PR contract + diff + "上轮输出非合法 JSON" 提示),不通过 `.reviewer_session` 发 system alert,不产生 session 文件

### Scenario 5: Gemini direct CLI 通过 generic renderer 执行(无回归)
- **Given** 环境变量 `LLM_DRIVER=gemini`
- **When** 任意 agent 角色被调用
- **Then** Gemini 通过 generic direct CLI renderer 执行,与重构前行为一致,现有测试全部通过

### Scenario 6: OpenClaw native 不受影响
- **Given** `LLM_DRIVER=openclaw`(或默认)
- **When** 任意 agent 角色被调用
- **Then** 通过现有 OpenClaw-native 路径执行,会话语义不变,`.coder_session` / session_map 继续正常工作

### Scenario 7: continuity_mode 合约校验
- **Given** engine config 中某 engine 的 `continuity_mode` 为 `mapped_resume`
- **When** `engine_registry.py` 加载并校验
- **Then** 校验失败,报 FATAL 错误,不启动任何子进程

### Scenario 8: direct_cli model 参数化规则
- **Given** 某 direct_cli engine entry 在 `execution.model_arg` 中定义了模型参数模板，并在 engine entry 中定义了 `default_model`
- **When** 通过 `SDLC_MODEL` 环境变量指定模型
- **Then** generic renderer 使用 `execution.model_arg` 模板传入该模型
- **And** 若 `execution.model_arg` 为 `null`，则 renderer 不传任何模型参数，`default_model` 也不构成必填要求


## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 核心质量风险
1. **Generic renderer 参数化错误**:模板字段映射错误导致 CLI 参数组装异常。
2. **Stateless retry 上下文丢失**:retry prompt 未正确注入上一轮输出,导致 agent 缺少修复所需信息。
3. **Gemini 回归**:迁移到 generic renderer 后 Gemini 行为改变。
4. **Session 文件残留**:stateless 引擎产生不应存在的 session 文件。

### Mock 策略
- `agy` 命令必须被 mock(通过 `mock_bin/agy` 或 `SDLC_MOCK_LLM_RESPONSE`),避免测试依赖宿主是否安装了 Antigravity CLI。
- Gemini 命令复用现有 mock 策略。
- OpenClaw 命令复用现有 mock 策略。

### 测试分层
- **Unit tests**:`engine_registry.py` 合约校验(新的 `continuity_mode` 枚举)、generic renderer 参数组装逻辑。
- **Sandbox E2E tests**:通过 mock CLI 走通 coder retry、reviewer retry 的 stateless 路径。
- **No live agy dependency**:测试不假设宿主安装了 agy。

### 下游质量信号
- 所有现有 test_agent_driver、test_engine_registry、test_orchestrator 测试继续通过。
- 新增 stateless retry 场景的 mock E2E 测试覆盖率。
- `preflight.sh` 全部通过。

## 6. Framework Modifications (框架防篡改声明)

- `scripts/agent_driver.py`:提取 generic direct CLI renderer;移除 `LLM_DRIVER=gemini` 特有分支(迁移到 generic renderer)
- `scripts/engine_registry.py`：`continuity_mode` 允许值从多值缩减为 `stateful | stateless`；`fallback_policy` 允许值加入 `fail_closed`；`handle_acquisition_strategy` 枚举保持不变（stateless 引擎继续使用 `unavailable`）
- `scripts/orchestrator.py`:`--engine` flag choices 支持 `agy`;direct CLI engine 的 retry 路径确保不依赖 session 文件
- `scripts/spawn_coder.py`:stateless retry 时注入上一轮 stdout
- `scripts/spawn_reviewer.py`:移除 `.reviewer_session` 依赖;`--system-alert` 路径改为 full re-prompt
- `scripts/envelope_assembler.py`:stateless retry 模式的 prompt assembly 支持
- `config/engines.default.json`:更新 Gemini entry 字段;新增加 agy entry

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)

- **v1.0**: 初始草案,基于 copilot 讨论 (2026-05-27)。讨论涉及:5 选项决策、continuity 模式简化、openab agy-acp wrapper 分析、JIT prompt stateless 兼容性审查、hybrid stateful/stateless 模型。
- **v1.1**: Coder-readiness check 审查决议 (2026-05-27)。6 项澄清:engine 命名映射、execution 字段存放、OpenClaw handle 字段不碰、coder retry stdout 来源、reviewer retry 实现方式、session 文件清除范围。全部纳入 §3.8 和决策表。
- **Audit Rejection (v1.1)**: Auditor 拒绝。架构方向正确,但 §7 不完全:缺 `cli_alias` 字段、execution subsection JSON shape、Gemini/agy 完整 args 模板、reviewer stateless retry alert 文本、`fallback_policy`/`capability_surface` 枚举决议;缺回滚/隔离策略。
- **v1.2 Revision Rationale**: 补全 §7 至 9 个小节覆盖所有新增字符串和模板；新增 §3.6 回滚与隔离策略（OpenClaw 零改动保证、Gemini 回滚改为配置级回滚、config overlay 可撤消、session 文件按引擎类型隔离）。决策表扩展至 D12。

---

## 7. Hardcoded Content (硬编码内容)

### 7.1 Contract Enum Values

- **For `engine_registry.py` - `ALLOWED_CONTINUITY_MODE_VALUES` replacement:**
```python
ALLOWED_CONTINUITY_MODE_VALUES = {"stateful", "stateless"}
```

- **For `engine_registry.py` - updated doc comment on `continuity_mode`:**
```python
# continuity_mode (str): "stateful" - engine natively returns a stable, authoritative,
# non-heuristic continuation handle with contractual guarantees.
# "stateless" - every invocation is independent one-shot; any continuation is
# provided by the orchestrator through explicit context injection.
```

- **For `engine_registry.py` - `ALLOWED_FALLBACK_POLICY_VALUES` replacement:**
```python
ALLOWED_FALLBACK_POLICY_VALUES = {"none", "legacy_direct_cli", "fail_closed_until_prerequisite_ready", "fail_closed"}
```

- **For `engine_registry.py` - `ALLOWED_HANDLE_ACQUISITION_STRATEGY_VALUES` (unchanged; stateless engines use `"unavailable"`):**
```python
ALLOWED_HANDLE_ACQUISITION_STRATEGY_VALUES = {"protocol_native", "explicit_returned_handle", "unavailable"}
```

- **For `engine_registry.py` - `ALLOWED_RUNTIME_MODE_VALUES` (unchanged):**
```python
ALLOWED_RUNTIME_MODE_VALUES = {"openclaw_native", "direct_cli", "acp"}
```

### 7.2 `cli_alias` Field Definition

- **For engine spec JSON - exact field name and placement (top-level engine entry):**
```json
{
  "engine_id": "agy_direct_cli",
  "cli_alias": "agy",
  ...
}
```

- **For `orchestrator.py` - `--engine` choices resolution logic (pseudocode):**
```python
# Build --engine choices from engine registry:
# for each engine entry, if cli_alias is present, use cli_alias;
# otherwise fall back to engine_id.
# Result for this PRD: ["openclaw", "gemini", "agy"]
# Mapping: {
#   "openclaw": "openclaw_native",
#   "gemini": "gemini_direct_cli",
#   "agy": "agy_direct_cli"
# }
```

### 7.3 `execution` Subsection - JSON Shape

- **For engine config - `execution` subsection shape (lives under the engine entry):**
```json
{
  "execution": {
    "executable": "agy",
    "one_shot_args": ["--print"],
    "model_arg": null,
    "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"},
    "permission_args": ["--dangerously-skip-permissions"],
    "sandbox_args": ["--sandbox"],
    "timeout_seconds": 300,
    "env_extra": {}
  }
}
```

注意:`execution` 字段**不进 `engine_registry.py` 的公开 schema 校验**。Generic renderer 在组装 CLI 命令时从合并后的 registry entry 中读取此 subsection。不存在的字段 renderer 使用合理默认值(空列表/null)。

### 7.4 Gemini Direct CLI Execution Template

- **For `config/engines.default.json` - Gemini `execution` subsection:**
```json
{
  "execution": {
    "executable": "gemini",
    "one_shot_args": ["--yolo", "-p"],
    "model_arg": {"flag": "--model", "value": "{model}"},
    "workspace_arg": null,
    "permission_args": [],
    "sandbox_args": [],
    "timeout_seconds": 3600,
    "env_extra": {}
  }
}
```

### 7.5 agy Direct CLI Execution Template

- **For `config/engines.local.json` - agy `execution` subsection:**
```json
{
  "execution": {
    "executable": "agy",
    "one_shot_args": ["--print"],
    "model_arg": {"flag": "--model", "value": "{model}"},
    "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"},
    "permission_args": ["--dangerously-skip-permissions"],
    "sandbox_args": ["--sandbox"],
    "timeout_seconds": 300,
    "env_extra": {},
    "default_model": "auto"
  }
}
```

### 7.6 Reviewer Stateless Retry - Exact Alert Text

- **For `orchestrator.py` - reviewer retry inline alert string (f-string format):**
```python
REVIEWER_RETRY_ALERT = (
    "SYSTEM ALERT: Your previous output could not be parsed as valid JSON. "
    "You MUST return ONLY a strict JSON object matching the required schema. "
    "No markdown formatting, no conversational text. "
    "Below is your previous raw output for reference. "
    "Do NOT repeat it. Produce a corrected JSON output.\n\n"
    "## PREVIOUS OUTPUT (NON-JSON)\n{previous_output}\n\n"
    "## REQUIRED SCHEMA\n{output_schema}"
)
```

### 7.7 Coder Stateless Retry - Prompt Template Fragment

- **For `spawn_coder.py` / `envelope_assembler.py` - previous stdout injection:**
```python
CODER_RETRY_PREVIOUS_OUTPUT_HEADER = (
    "\n\n## PREVIOUS CODER OUTPUT\n"
    "Your previous execution produced the following output. "
    "Use it as context for this retry. "
    "Do NOT repeat the same mistakes. Address the system alert below.\n\n"
    "{previous_stdout}"
)
```

### 7.8 Complete agy Engine Entry (Public Example)

- **For `config/engines.default.json` - agy public example:**
```json
{
  "engines": {
    "agy_direct_cli": {
      "engine_id": "agy_direct_cli",
      "cli_alias": "agy",
      "display_name": "Antigravity CLI (agy)",
      "runtime_mode": "direct_cli",
      "registration_visibility": "public",
      "continuity_mode": "stateless",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "fail_closed",
      "capability_surface": "client_mediated",
      "execution": {
        "executable": "agy",
        "one_shot_args": ["--print"],
        "model_arg": {"flag": "--model", "value": "{model}"},
        "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"},
        "permission_args": ["--dangerously-skip-permissions"],
        "sandbox_args": ["--sandbox"],
        "timeout_seconds": 300,
        "env_extra": {},
        "default_model": "auto"
      }
    }
  }
}
```

### 7.9 Complete Gemini Engine Entry (Post-Migration Reference)

- **For `config/engines.default.json` - Gemini full entry after stateless migration:**
```json
{
  "engines": {
    "gemini_direct_cli": {
      "engine_id": "gemini_direct_cli",
      "cli_alias": "gemini",
      "display_name": "Gemini Direct CLI",
      "runtime_mode": "direct_cli",
      "registration_visibility": "public",
      "continuity_mode": "stateless",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "fail_closed",
      "capability_surface": "client_mediated",
      "execution": {
        "executable": "gemini",
        "one_shot_args": ["--yolo", "-p"],
        "model_arg": {"flag": "--model", "value": "{model}"},
        "workspace_arg": null,
        "permission_args": [],
        "sandbox_args": [],
        "timeout_seconds": 3600,
        "env_extra": {}
      }
    }
  }
}
```
