---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: OpenClaw Thinking Level CLI Contract and Test Alignment

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前已经在 OpenClaw agent invocation 路径中实际使用 `--thinking high`，但这个能力并没有作为一个正式、显式、可审计的 CLI / execution contract 被定义，而是以实现细节的形式先被手工引入。结果是：

- 上游入口没有统一、显式地暴露该参数；
- 下游 `agent_driver` 已经把 `--thinking high` 拼进 OpenClaw 命令；
- 测试仍然按旧命令形态断言 `-m` 直接跟在 `--session-id` 后面；
- 导致 `tests/test_079_agent_driver_openclaw_lazy_create.py` 与 `tests/test_083_openclaw_model_aware_routing.py` 出现稳定失败。

当前本地直接运行：
- `tests/test_079_agent_driver_openclaw_lazy_create.py`
- `tests/test_083_openclaw_model_aware_routing.py`
- `tests/test_spawn_auditor.py`

结果表明：
- 失败集中在 `079` / `083` 中与 OpenClaw argv 形态相关的断言；
- 当前已知失败的共同根因不是产品逻辑错误，而是：

> **`thinking` 已经成为事实上的 OpenClaw 执行参数，但还不是正式 contract，因此入口参数、真实多跳传递链和测试断言没有同步收敛。**

这里的真实链路不是单跳：
- orchestrator 不会直接调用 `invoke_agent()`；
- 它会通过 `spawn_planner.py` / `spawn_coder.py` / `spawn_reviewer.py` / `spawn_verifier.py` / `spawn_manager.py` / `spawn_arbitrator.py` 等入口间接走到 `agent_driver.invoke_agent()`；
- auditor 也通过 `spawn_auditor.py -> agent_driver.invoke_agent()` 进入同一执行层。

本 PRD 的目标不是实现完整的 role-specific execution profile 系统，也不是统一所有引擎的 thinking 行为，而是：

> **把 OpenClaw thinking level 提升为正式 CLI/execution contract：所有真实 `spawn_*` entrypoint 都显式接收 `--thinking`，通过单一共享 resolver 应用唯一默认值 `high`，再把解析后的 thinking 显式传给 `agent_driver.invoke_agent()`，且该 contract 当前仅对 `openclaw` 引擎生效。**

本 PRD 不覆盖：
- Gemini 或其它非 OpenClaw 引擎的 thinking-level 语义统一；
- broader agent-driver / routing cleanup；
- 与 thinking 参数无关的其它 pytest debt；
- role-specific profile matrix（例如为 planner/coder/reviewer/verifier 分别设计复杂默认策略）。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须把 OpenClaw thinking level 定义为正式 CLI 参数与统一内部 contract**
   - 所有真实会直接调用 `agent_driver.invoke_agent()` 的 `spawn_*` entrypoint 都必须支持 `--thinking` 参数；
   - `orchestrator.py` 与 `spawn_auditor.py` 作为上游入口，也必须支持该参数并把它显式传给各自调用的下游 `spawn_*` 或直接调用链；
   - 该参数默认值必须是 `high`；
   - 允许值必须严格限制为：
     - `low`
     - `medium`
     - `high`
     - `xhigh`

2. **thinking 参数当前只对 OpenClaw 引擎生效**
   - 当执行引擎为 `openclaw` 时，thinking level 必须被传递并体现在最终 agent invocation 命令中；
   - 当执行引擎不是 `openclaw` 时，该参数可以被解析但不要求实现等价 thinking 参数映射；
   - 不允许在这轮工作中顺手扩张到 Gemini / 其它引擎的统一参数治理。

3. **必须选择唯一、显式、无环境歧义的传播机制**
   - 本轮唯一允许的传播机制是：**CLI 参数逐层显式传递 + 共享 resolver 单点应用默认值**；
   - 不使用模糊的 ambient env bridge 作为 canonical carrier；
   - `thinking` 的 canonical owner 是共享 resolver / helper：它是唯一允许应用默认值 `high` 和校验 allowed set 的地方；
   - 各个 entrypoint 只能调用该 shared resolver 获取最终 thinking 值，不得自行 fallback 或再次定义默认值。

4. **必须定义 direct invocation behavior for every real spawn entrypoint**
   - 当 `spawn_planner.py` / `spawn_coder.py` / `spawn_reviewer.py` / `spawn_verifier.py` / `spawn_manager.py` / `spawn_arbitrator.py` / `spawn_auditor.py` 被直接调用时：
     - 它们都必须接受 `--thinking`；
     - 如果调用方未显式提供，则由共享 resolver 在该 entrypoint 层应用唯一默认值 `high`；
     - 然后把已解析、已校验的最终值显式传给 `invoke_agent()`；
   - `agent_driver` 不得再承担“猜默认值”职责。

5. **必须修复测试，使其验证正式 contract 而不是旧 argv 位置假设**
   - `tests/test_079_agent_driver_openclaw_lazy_create.py` 必须不再依赖 `-m` 紧跟在 `--session-id` 后面的旧顺序假设；
   - `tests/test_083_openclaw_model_aware_routing.py` 必须同样更新为验证 thinking-aware 的正式 OpenClaw command shape；
   - 测试应验证：
     - 默认 thinking 为 `high`
     - 显式 thinking 参数被正确透传
     - 相关 OpenClaw routing / agent id 行为仍然成立

6. **必须对非法 thinking 值 fail closed**
   - 非法 thinking 值不得被悄悄接受；
   - 应由共享 resolver / CLI 参数层拒绝，而不是留给下游实现猜测。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 只处理 thinking contract 所必需的入口、传递链和对应测试；
   - 不应顺带重构整个 agent-driver / execution profile 系统。

2. **默认行为必须稳定且显式**
   - 对 OpenClaw 引擎而言，不传 thinking 时的默认行为必须清晰、单一、可测试；
   - 不允许不同入口对默认值理解不一致。

3. **测试必须对齐 contract，而不是对齐偶然的实现细节**
   - 断言应验证命令中存在正确的 `--thinking <value>` 语义；
   - 不应继续把旧 argv 索引顺序误当成不变 contract。

### User Stories

- **As a maintainer**, I want `thinking` to be a formal OpenClaw execution contract rather than a stealth implementation detail, so behavior and tests stay aligned.
- **As a reviewer**, I want default and explicit thinking-level behavior to be externally verifiable from CLI inputs through final OpenClaw argv construction, so regressions are caught at the right layer.
- **As an engineer**, I want tests to validate the intended command contract (`--thinking <value>` for OpenClaw) instead of an outdated token order, so small implementation evolution does not produce misleading failures.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **explicit CLI threading + shared resolver** 路线：
- 把 thinking level 从底层隐式硬编码上升为所有真实 `spawn_*` entrypoint 的正式 CLI 参数；
- 使用一个共享 resolver 作为 canonical owner，统一应用默认值 `high` 与 allowed-set 校验；
- 通过 CLI 参数逐层显式传递，而不是依赖 ambient env state；
- 将解析后的 thinking 显式透传到 `agent_driver.invoke_agent()` / OpenClaw argv 组装层；
- 测试验证默认值、显式值和非法值，而不是旧 argv 假设。

### 3.1 核心设计决策

1. **当前只给 OpenClaw 建正式 contract，不扩张到其它引擎**
   - 这是当前真实问题所在；
   - 把范围限制在 OpenClaw，可以避免这轮工作滑向多引擎参数统一治理。

2. **默认值 `high` 必须由共享 resolver 单点应用**
   - 这样上游入口、各个 `spawn_*` 包装层、下游 agent_driver、测试、以及后续审计都能围绕同一个 contract 收敛；
   - 不允许 orchestrator、auditor、planner、coder、reviewer、verifier 等各自私下再定义默认值。

3. **必须把真实调用链写闭环，而不是只改最上游两个入口**
   - 当前实际会走到 `invoke_agent()` 的入口包括：
     - `spawn_auditor.py`
     - `spawn_planner.py`
     - `spawn_coder.py`
     - `spawn_reviewer.py`
     - `spawn_verifier.py`
     - `spawn_manager.py`
     - `spawn_arbitrator.py`
   - `orchestrator.py` 不是最终调用点本身，而是这些 `spawn_*` 的调度上游；
   - 因此这轮 contract 必须明确：各个 entrypoint 都接收 `--thinking`，通过同一个 resolver 归一化后，再显式传入 `invoke_agent()`。

4. **测试应该验证语义而不是脆弱索引**
   - 当前失败暴露出旧测试把 `-m` 的位置误当成了 contract；
   - 修复后测试应该验证：命令包含正确的 `--thinking <value>`，且消息参数仍被正确传入。

5. **四档 thinking 必须被定义为 deliberate internal subset**
   - 这四个值不是临时猜测，而是本轮明确支持的内部 contract；
   - 非法值必须 fail closed，防止 wrapper contract 漂移成“看似支持一切，实际行为不确定”。

### 3.2 推荐实现方向

#### A. Canonical owner and propagation mechanism
- 使用一个共享 resolver / helper 作为唯一 canonical owner，负责：
  - 应用默认值 `high`
  - 校验 allowed values (`low / medium / high / xhigh`)
  - 返回最终规范化的 thinking level
- 唯一允许的跨层传播机制是：**CLI 参数逐层显式传递**；
- 不使用未指定、可漂移的 ambient env bridge 作为 canonical carrier。

#### B. CLI entrypoints
- 在以下真实 entrypoint 中统一增加 `--thinking` 参数，默认值通过共享 resolver 生效：
  - `scripts/orchestrator.py`
  - `scripts/spawn_auditor.py`
  - `scripts/spawn_planner.py`
  - `scripts/spawn_coder.py`
  - `scripts/spawn_reviewer.py`
  - `scripts/spawn_verifier.py`
  - `scripts/spawn_manager.py`
  - `scripts/spawn_arbitrator.py`
- 对本轮实际会从 `orchestrator` 链路走到 `invoke_agent()` 的 `spawn_*` 入口，必须显式接收并继续传递 thinking，而不是依赖隐藏状态。

#### C. Propagation layer
- `orchestrator.py` 调用各个 `spawn_*` 时，必须显式传入 `--thinking <value>`；
- `spawn_auditor.py` 直接作为 entrypoint 调用时，也必须通过同一个 shared resolver 得到 thinking，并显式传入 `invoke_agent()`；
- 所有其它真实 `spawn_*` 在 direct invocation 场景下也必须通过同一个 shared resolver 处理 thinking，再显式传给 `invoke_agent()`；
- `agent_driver` 不负责默认值决策，只消费已经规范化后的 thinking 值。

#### D. OpenClaw invocation layer
- 当 driver / engine 为 `openclaw` 时，最终命令必须显式包含：
  - `--thinking <value>`
- 当 driver / engine 不是 `openclaw` 时，该参数可以被忽略，不要求等价透传。

#### E. Tests
- 更新 `tests/test_079_agent_driver_openclaw_lazy_create.py`：
  - 验证默认 thinking 为 `high`
  - 验证显式 thinking 被正确透传
  - 不再使用旧的 `cmd[:7] == ... '-m'` 脆弱断言
- 更新 `tests/test_083_openclaw_model_aware_routing.py`：
  - 验证 model-aware routing 仍成立
  - 同时验证 thinking-aware command shape
- 补一个 very narrow 的端到端入口测试：
  - 至少证明 `orchestrator` 路径和 `spawn_auditor` 路径最终都会生成一致的 OpenClaw `--thinking <value>` command shape。
- 如有需要，补一个 very narrow 的非法值解析测试，证明 CLI 边界会拒绝超出四档的 thinking 值。

### 3.3 明确不采用的方案

1. **不只是修改测试去接受当前隐式行为**
   - 只改测试会把“未设计完的实现细节”合法化，而不是建立正式 contract。

2. **不把这轮工作扩张成多引擎统一 thinking 系统**
   - 当前只对 OpenClaw 生效，这是刻意限制范围。

3. **不继续依赖 argv 旧顺序假设**
   - `-m` 是否紧跟 `--session-id` 不应继续被视为 contract 本体。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: OpenClaw entrypoints accept an explicit thinking-level parameter**
  - **Given** an OpenClaw-driven execution entrypoint such as orchestrator or auditor
  - **When** `--thinking` is omitted
  - **Then** the effective OpenClaw thinking level defaults to `high`

- **Scenario 2: Allowed OpenClaw thinking values are passed through explicitly**
  - **Given** an OpenClaw-driven execution entrypoint
  - **When** `--thinking` is set to one of `low`, `medium`, `high`, or `xhigh`
  - **Then** the final OpenClaw agent invocation includes `--thinking <value>` with the exact requested value

- **Scenario 3: Invalid thinking values fail closed**
  - **Given** an OpenClaw-driven execution entrypoint
  - **When** an unsupported thinking value is supplied
  - **Then** the command is rejected before execution rather than silently falling back or proceeding ambiguously

- **Scenario 4: Agent-driver tests validate thinking-aware contract rather than legacy token ordering**
  - **Given** the OpenClaw agent-driver unit tests
  - **When** they inspect the constructed command
  - **Then** they confirm the presence and correctness of `--thinking <value>` and message delivery
  - **And** they do not fail merely because `-m` is no longer immediately adjacent to `--session-id`

- **Scenario 5: Model-aware OpenClaw routing still works under the new contract**
  - **Given** model-specific OpenClaw agent selection logic
  - **When** a supported OpenClaw model is requested with the default or explicit thinking level
  - **Then** the correct agent id is still selected
  - **And** the thinking parameter is added without breaking routing behavior

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
当前最大的风险不是“多一个参数”，而是：

1. 底层实现已经暗中引入了 thinking 行为，但上游入口、真实 `spawn_*` 传递链和测试没有形成正式 contract；
2. 只改测试会把隐式行为固化，而不是把接口设计补齐；
3. 如果默认值、显式值、非法值三类行为没有一起测试，就会再次出现入口与实现分叉；
4. 如果 orchestrator 路径与 auditor 路径各自实现 thinking，而没有单一 source of truth，就会形成 wrapper contract drift。

### Verification Strategy

#### A. Focused unit/contract verification
优先验证：
- `tests/test_079_agent_driver_openclaw_lazy_create.py`
- `tests/test_083_openclaw_model_aware_routing.py`
- 与 CLI 参数解析相关的入口测试（如需要，可补充 orchestrator / auditor focused tests）

#### B. End-to-end propagation verification
必须明确覆盖：
- 默认值 `high`
- 显式值 `low / medium / high / xhigh`
- 非法值 reject
- OpenClaw 路径确实带出 `--thinking <value>`
- `orchestrator` 路径和 `spawn_auditor` 路径最终都收敛到同一个 OpenClaw command shape
- direct invocation of every real `spawn_*` does not reintroduce duplicated defaults or hidden fallback logic

#### C. Scope control
如果现有其它 ignored tests（例如 `tests/test_spawn_auditor.py`）没有因为 thinking contract 直接失败，不必把它们强行纳入同一波治理；当前优先目标是把 `079` / `083` 这组已知失败收敛掉，同时把 contract 传递链写闭环。

### Quality Goal
本 PRD 的质量目标不是“一次整理所有 agent execution 参数”，而是：

> **把 OpenClaw thinking level 从隐式实现细节升级为正式 CLI/execution contract，并让当前已知失败测试改为验证这个正式 contract。**

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/spawn_auditor.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_coder.py`
- `scripts/spawn_reviewer.py`
- `scripts/spawn_verifier.py`
- `scripts/spawn_manager.py`
- `scripts/spawn_arbitrator.py`
- `scripts/agent_driver.py`
- one shared resolver/helper module for thinking normalization and default application (if needed)
- `tests/test_079_agent_driver_openclaw_lazy_create.py`
- `tests/test_083_openclaw_model_aware_routing.py`
- any narrow focused test file for entrypoint CLI parsing / end-to-end propagation (only if directly needed)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 观察到 OpenClaw invocation 已经事实性带上 `--thinking high`，但该能力未作为正式 CLI/execution contract 建模，导致 `test_079` / `test_083` 失败。
- **v1.1 Scope Clarification**: 明确这轮只对 OpenClaw 引擎生效，不扩展到 Gemini / 其它引擎。
- **v1.2 Contract Decision**: thinking 参数上升为正式入口参数，默认值为 `high`，allowed set 固定为 `low / medium / high / xhigh`，测试改为验证 contract 而不是旧 argv 位置。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **For the exact allowed OpenClaw thinking values:**
```text
low
medium
high
xhigh
```

- **For the exact OpenClaw-only default thinking value:**
```text
high
```

- **For the exact focused failing test files this PRD must bring into alignment:**
```text
tests/test_079_agent_driver_openclaw_lazy_create.py
tests/test_083_openclaw_model_aware_routing.py
```

- **For the exact CLI parameter name that must be exposed by entrypoints:**
```text
--thinking
```

