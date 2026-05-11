---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Startup Validation Guardrail Runtime Root Allowlist

## 1. Context & Problem (业务背景与核心痛点)
当前 `leio-sdlc` 的 startup validation guardrail 对“合法 installed runtime”与“源码 workspace 执行”之间的区分方式过于脆弱，并且隐含了 `.openclaw/skills` 是唯一合法 runtime surface 的假设。

在多个入口脚本中，当前逻辑形态大致类似：

```python
if not args.enable_exec_from_workspace and not sys.argv[0].startswith(getattr(config, "SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))):
    ... fatal startup validation failure ...
```

这会导致两个问题：

1. **guardrail 实际上是在验证一个硬编码路径形状，而不是验证合法 installed runtime 语义**
   - 它把 `.openclaw/skills` 风格路径隐含当成唯一合法启动面；
   - 这不是“授权 runtime root”语义，而是“路径字符串长得像旧默认目录”语义。

2. **合法 alternate runtime surface 会被误杀**
   - 当 `leio-sdlc` 被安装或挂载在其他 runtime surface 下，例如：
```text
~/.gemini/skills
```
   - 即使这是合法 installed runtime，也可能被 startup validation 错误拒绝；
   - 结果就是：不是 workspace 执行，却被当成 workspace/unauthorized execution 拦掉。

这类问题已经在真实操作中出现：从 repo workspace 启动会被 guardrail 拦住，这是对的；但如果从 alternate installed runtime surface（如 `.gemini/skills`）启动也被拒绝，就说明 guardrail 的 contract 写错了。

本 PRD 的目标不是重做安装器，也不是做完整的多 runtime 自动发现系统，而是把 startup validation 修正为一个**最小、可审计、统一的 runtime-root allowlist contract**：

- 允许从 runtime config 声明的合法 installed roots 启动；
- 默认内建兼容 `.openclaw/skills` 与 `.gemini/skills`；
- 继续拒绝普通源码 workspace 执行，除非显式 `--enable-exec-from-workspace`；
- 统一所有主要 entrypoints 的 guardrail，避免各自复制漂移。

本 PRD **不处理**：
- 环境变量级 runtime root override；
- install-time 自动探测 OpenClaw/Gemini/Codex 等 runtime 是否存在；
- 多 runtime registry / activation framework；
- GitHub integration；
- 放松 `--enable-exec-from-workspace` 安全规则；
- 用“判断当前是否 git repo”来替代 runtime authorization 逻辑。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须冻结 startup validation 的授权语义**
   - startup validation 判断的对象必须是：
     - 当前 entrypoint 是否位于一个 **authorized installed runtime root** 之下；
   - 而不是：
     - 当前路径是否看起来像 `.openclaw/skills`；
     - 当前目录是否是 git repo；
     - 当前路径 basename 是否符合某种约定俗成的名字。

2. **必须引入 runtime config 驱动的 allowlist**
   - 需要一个 runtime-side config 字段来声明合法 runtime roots；
   - 推荐字段名：
```text
ALLOWED_RUNTIME_ROOTS
```
   - 该字段为字符串数组，每一项代表一个合法 installed runtime root；
   - 该字段的配置承载面必须明确绑定到现有配置链：
     - `config/sdlc_config.json.template`
     - `config/sdlc_config.json`

3. **当 runtime config 缺少 `ALLOWED_RUNTIME_ROOTS` 时，必须有兼容性的默认 allowlist**
   - 缺省必须等价于：
```text
~/.openclaw/skills
~/.gemini/skills
```
   - 也就是说，如果没有显式配置 `ALLOWED_RUNTIME_ROOTS`，startup validation 仍然必须接受这两个 built-in runtime roots；
   - 这是兼容性 default，不代表系统必须探测这两个目录都存在。

4. **`--enable-exec-from-workspace` override 语义必须保持不变**
   - 当显式传入 `--enable-exec-from-workspace` 时，仍然允许从 workspace/source checkout 启动；
   - 本 PRD 不授权弱化这个 override，也不授权删除它。

5. **workspace execution 在无 override 时必须继续被拒绝**
   - 即使引入了 runtime root allowlist，也不能让普通源码目录启动被放行；
   - 从 repo checkout 路径启动，若未显式传 `--enable-exec-from-workspace`，仍然必须触发 startup validation failure。

6. **主要 entrypoints 的 guardrail contract 必须统一**
   - 不允许只修 `orchestrator.py`，其余 `spawn_*` 继续保留旧逻辑；
   - 至少以下入口必须对齐：
     - `scripts/orchestrator.py`
     - `scripts/spawn_auditor.py`
     - `scripts/spawn_planner.py`
     - `scripts/spawn_coder.py`
     - `scripts/spawn_reviewer.py`
     - `scripts/spawn_verifier.py`
     - `scripts/spawn_manager.py`
     - `scripts/spawn_arbitrator.py`

7. **路径判断必须先规范化，并使用 segment-safe ancestry / true parent-child containment**
   - 对当前脚本路径和 allowed runtime roots，必须先做：
     - `expanduser(...)`
     - `abspath(...)`
     - `realpath(...)`（或等价规范化）
   - 授权判断必须基于 **segment-safe ancestry semantics**（例如 `commonpath`、`Path.parents`、或等价的 true parent/child containment 语义）；
   - **严禁任何形式的字符串前缀授权逻辑**，无论路径是否已规范化；
   - 不允许继续使用任何基于字符串 `startswith(...)` 或等价 prefix matching 的授权判断。

### Non-Functional Requirements

1. **本 PRD 必须是最小修复，不得膨胀为 runtime 安装/发现系统**
   - 不做 install-time auto detection；
   - 不做环境变量 override；
   - 不做 runtime registry 平台重构；
   - 不做 Codex / future runtimes 的自动接入机制。

2. **默认值必须被明确视为 built-in compatibility defaults**
   - `~/.openclaw/skills` 与 `~/.gemini/skills` 是 startup validation 的兼容性默认 allowlist；
   - 不是“必须存在”或“启动前必须探测到”的运行时依赖。

3. **不得用 git presence 代替授权判断**
   - 不能通过“有无 `.git`”来判断是不是源码目录；
   - 不能通过 repo 特征去猜测 installed/runtime vs workspace/source。

4. **实现必须避免各入口再度漂移**
   - 必须抽取一个 shared helper 作为 startup authorization 的**唯一合法实现入口**；
   - 不允许在每个入口各自复制一份授权逻辑；
   - 不允许 `orchestrator.py` 与任何 `spawn_*` 继续各用一套规则。

### User Stories

- **As an operator**, I want `leio-sdlc` to launch successfully from a legitimate installed runtime surface such as `~/.gemini/skills`, so the guardrail no longer falsely rejects a valid non-workspace runtime.
- **As a maintainer**, I want startup validation to use one explicit allowlist contract instead of ad-hoc `.openclaw` path assumptions, so alternate installed runtimes do not break silently.
- **As a reviewer**, I want workspace execution to remain blocked unless explicitly overridden, so this fix does not accidentally weaken the safety boundary while broadening installed-runtime compatibility.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **runtime-root allowlist + shared guardrail helper** 路线，而不是“多 runtime 自动发现系统”路线。

### 3.1 冻结的 authoritative contract

#### A. Authoritative allowed runtime roots
startup validation 的合法 installed runtime surface 必须来自 runtime-side config 字段：
```text
ALLOWED_RUNTIME_ROOTS
```

如果该字段存在，则它是唯一权威来源。

#### B. Built-in compatibility defaults
如果 runtime config 缺少 `ALLOWED_RUNTIME_ROOTS`，则默认 allowlist 必须是：
```text
~/.openclaw/skills
~/.gemini/skills
```

这两个 default：
- 是兼容性授权面；
- 不是必须存在的物理目录；
- 不要求启动前去探测其存在性。

#### C. Path normalization and segment-safe containment contract
对每一个 candidate root 与当前 entrypoint 路径，都必须统一做：
```text
expanduser -> abspath -> realpath
```
然后再做**segment-safe parent/child containment** 判定。

强制约束：
- 授权判断必须基于 `commonpath`、`Path.parents`、或等价的 true parent/child containment 语义；
- **严禁任何形式的字符串前缀授权逻辑**，即使路径已经过规范化；
- `~/.gemini/skills-evil` 这类 false-prefix path 绝不能因为文本前缀相似而被授权。

#### D. Workspace override contract
- 若传入 `--enable-exec-from-workspace`，则允许绕过 installed-runtime allowlist 检查；
- 否则，只有位于 allowed runtime roots 之下的 entrypoint 才允许启动。

### 3.2 具体改动方向

#### A. Config surface
需要在现有 runtime-side config 链中新增/支持：
```text
ALLOWED_RUNTIME_ROOTS
```
类型：字符串数组。

配置承载面必须明确绑定到：
- `config/sdlc_config.json.template`
- `config/sdlc_config.json`

缺省语义：
- 若字段缺失，则使用 built-in defaults：
  - `~/.openclaw/skills`
  - `~/.gemini/skills`

本 PRD 不要求：
- 环境变量 override
- 动态写入/注册逻辑
- 安装器自动维护该列表

#### B. Shared helper (mandatory single source of truth)
必须新增或统一一个 shared helper，作为 startup validation authorization 的**唯一合法实现入口**。其职责包括：
1. 解析并返回 canonical allowed runtime roots
2. 判断当前 entrypoint 是否位于 allowlist 之一下面

推荐 helper 语义：
- `resolve_allowed_runtime_roots(...)`
- `is_authorized_runtime_launch(script_path, allowed_roots)`

强制约束：
- 所有 startup validation entrypoints **必须且只能** 通过该 shared helper 执行授权判断；
- 不允许任何入口保留本地复制的授权逻辑；
- 不允许 `orchestrator.py` 与各 `spawn_*` 使用不同判断路径；
- 不允许把 helper 仅作为“可选复用建议”。

#### C. Entry points to update
至少以下入口必须统一改成调用该 shared helper：
- `scripts/orchestrator.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_manager.py`
- `scripts/spawn_arbitrator.py`

#### D. Explicitly rejected strategies
本 PRD 明确不采用：

1. **把 `.gemini` 再硬编码进每个入口 if/else**
   - 这只是从一个硬编码扩成两个硬编码，不是 contract 修复。

2. **靠 git / `.git` 判断是不是 workspace**
   - 这不能可靠区分 installed runtime 与 workspace/source checkout。

3. **扩张成 runtime auto-discovery / activation framework**
   - 这会把一个小 bug 变成平台工程。

4. **使用任何形式的字符串前缀授权逻辑**
   - 即使先做了 `expanduser/abspath/realpath`，也不允许再用字符串 prefix matching 代替 true parent/child containment。

### 3.3 Why this is enough for #45
issue #45 当前要解决的是：
- `.openclaw` 硬编码造成合法 alternate runtime（如 `.gemini/skills`）被误杀。

因此这次只需要做到：
- startup validation 接受 runtime config allowlist；
- 无配置时默认允许 `.openclaw/skills` 与 `.gemini/skills`；
- 不放松 workspace safety rule。

不需要在这一轮内解决：
- future runtimes 自动接入
- env override
- install-time probing
- registry/activation orchestration

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: installed runtime launch under `.openclaw/skills` remains allowed by default**
  - **Given** no explicit `ALLOWED_RUNTIME_ROOTS` is configured
  - **And** the entrypoint path is under `~/.openclaw/skills`
  - **When** startup validation runs without `--enable-exec-from-workspace`
  - **Then** startup validation passes

- **Scenario 2: installed runtime launch under `.gemini/skills` is allowed by default**
  - **Given** no explicit `ALLOWED_RUNTIME_ROOTS` is configured
  - **And** the entrypoint path is under `~/.gemini/skills`
  - **When** startup validation runs without `--enable-exec-from-workspace`
  - **Then** startup validation passes

- **Scenario 3: workspace/source checkout launch remains blocked without explicit override**
  - **Given** the entrypoint path is under a project workspace checkout rather than an allowed runtime root
  - **When** startup validation runs without `--enable-exec-from-workspace`
  - **Then** startup validation fails
  - **And** the failure remains attributable to workspace/unauthorized launch rather than being silently allowed

- **Scenario 4: configured runtime allowlist changes observable authorization outcomes**
  - **Given** runtime config explicitly sets `ALLOWED_RUNTIME_ROOTS` in the `config/sdlc_config.json.template` / `config/sdlc_config.json` config chain to a list that contains only one allowed runtime root
  - **And** an entrypoint path under that configured root
  - **When** startup validation runs without `--enable-exec-from-workspace`
  - **Then** startup validation passes
  - **And** an entrypoint path that is only covered by the built-in default roots but not by the explicit configured allowlist is rejected

- **Scenario 5: false-prefix paths are never authorized**
  - **Given** an allowed runtime root such as `~/.gemini/skills`
  - **And** an entrypoint path that only shares the same textual prefix, such as a path under `~/.gemini/skills-evil`
  - **When** startup validation runs without `--enable-exec-from-workspace`
  - **Then** startup validation fails
  - **And** textual prefix resemblance does not count as authorization

- **Scenario 6: canonical containment follows real parent/child ancestry rather than path appearance**
  - **Given** an entrypoint path whose raw text appearance could be misleading before canonical resolution
  - **When** startup validation runs
  - **Then** authorization is decided using canonical realpath-based parent/child containment semantics
  - **And** not by string prefix resemblance or non-canonical path appearance

- **Scenario 7: all major entrypoints share the same authorization contract**
  - **Given** two different SDLC entrypoints such as `orchestrator.py` and `spawn_auditor.py`
  - **When** both are launched from the same allowed runtime root
  - **Then** both are accepted
  - **And** when both are launched from the same unauthorized workspace path without override, both are rejected

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是单个脚本的小 if 错误，而是 **startup validation contract 在多个 entrypoints 上继续漂移**：
- 一个入口认 `.gemini`，另一个入口还只认 `.openclaw`；
- 一个入口做路径规范化，另一个入口继续用裸 `startswith`；
- workspace 执行安全边界在某些入口上被意外放松。

### 推荐测试策略

1. **优先做 contract-level unit/integration tests**
   - 对 shared helper 做路径规范化与 containment contract 测试；
   - shared helper 不是建议性抽象，而是 startup authorization 的唯一实现入口；
   - 对至少一个或两个代表性入口做 CLI / startup validation 层测试，证明所有主要入口确实通过同一 helper 生效。

2. **路径样本必须覆盖默认双 root、workspace 拒绝与 false-prefix 回归**
   - `~/.openclaw/skills/...` → pass
   - `~/.gemini/skills/...` → pass
   - workspace path → fail
   - `~/.gemini/skills-evil/...` 这类 false-prefix path → fail

3. **必须覆盖 canonical containment 场景**
   - 需要验证授权判断基于 canonical realpath parent/child containment，而不是文本前缀或未规范化路径外观。

4. **不要过度依赖真实机器目录存在性**
   - 这些 roots 只是 allowlist contract，不要求真实存在；
   - 测试应侧重路径语义，而不是依赖宿主环境上真的安装了 openclaw/gemini。

5. **必须验证多入口的一致性**
   - 至少要证明 `orchestrator.py` 和一个 `spawn_*` 入口不会再各用一套规则。

### Quality Goal
修复完成后，startup validation 必须达到：
- alternate installed runtime（尤其 `.gemini/skills`）不再被误杀；
- workspace safety guardrail 仍然保留；
- 主要 entrypoints 的启动授权逻辑不再漂移。

## 6. Framework Modifications (框架防篡改声明)
- `config/sdlc_config.json.template`
- `config/sdlc_config.json`（通过现有 config merge chain 承载 `ALLOWED_RUNTIME_ROOTS`）
- `scripts/config.py`
- `scripts/orchestrator.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_manager.py`
- `scripts/spawn_arbitrator.py`
- 承载 startup authorization 单点收口逻辑的 shared helper 文件
- 与 startup validation contract 直接相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 采用 runtime config allowlist + built-in defaults（`~/.openclaw/skills`, `~/.gemini/skills`）的最小修复策略，拒绝扩张到 env override 或 runtime auto-discovery。
- **Audit Rejection (v1.0)**: None yet.
- **v2.0 Revision Rationale**: Pending auditor feedback if needed.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`startup_validation_config_key`**:
```text
ALLOWED_RUNTIME_ROOTS
```

- **`built_in_default_allowed_runtime_roots`**:
```text
~/.openclaw/skills
~/.gemini/skills
```

- **`workspace_override_flag`**:
```text
--enable-exec-from-workspace
```
