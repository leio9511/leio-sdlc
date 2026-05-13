---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Case-1-Only Engine Support for Strong Continuity

## 1. Context & Problem (业务背景与核心痛点)

`leio-sdlc` 当前在多引擎 continuity / resume 语义上存在一个非常关键但此前被表述得不够准确的问题。

最初我们把问题聚焦在 Gemini CLI 的这个调用上：

```bash
gemini --list-sessions -o json
```

并认为问题主要是：它返回的不是可直接 `json.loads()` 的 JSON session inventory。

这个观察本身并没有错，但经过更完整的 live 实验后，我们确认：**这还不是最核心的问题**。

### 已验证事实

1. **Gemini 确实支持 resume**
   - `gemini -r <session-id>` 可用
   - `gemini -r latest` 可用
2. **但 `gemini --list-sessions -o json` 仍然不能被视为可靠的 JSON inventory contract**
   - 当前 live 结果仍然是文本格式 session 列表，而不是可直接作为 machine-safe inventory 使用的 JSON 数组
3. **即使成功 parse 文本列表，也仍然无法回答 correctness 的核心问题**

> 当刚启动一个新的 Gemini session 之后，`leio-sdlc` 如何 100% 确认哪个 provider session id 就是这次 invocation 对应的真实 session？

这就是当前架构上的真正 blocker。

### 为什么原思路不够

当前旧思路本质上依赖一种 post-hoc discovery 模型：
- 先启动 session
- 然后调用 `--list-sessions`
- 再从输出里匹配、猜测、推断出“应该是这个 session id”

这个模型的问题不是只有 JSON/text 解析，而是它缺乏 **bootstrap-time authoritative identity acquisition**：
- prompt-preview 匹配不是 100%
- `latest` 不是 100%
- index 不是 100%
- 时间窗口不是 100%
- 并发 / retry / 历史残留时都会失真

所以，问题的本质已经不是“Gemini 会不会 resume”，而是：

> **如果 engine 在 session 创建时不能 authoritative 地返回 resume id，那么 `leio-sdlc` 就不能对该 engine 提供强 continuity 正确性承诺。**

### 产品层面的结论

与其继续声称“理论上支持很多引擎”，但把 correctness 建在 heuristic matching 上，不如明确收窄支持边界：

> **当前 `leio-sdlc` 仅支持 case-1 engine 的 strong continuity。**

这是一条更诚实、也更可执行的产品边界。

## 2. Requirements & User Stories (需求定义)

### Functional Requirements

**FR-1: `leio-sdlc` 仅支持 case-1 engine 的 strong continuity**
系统必须明确限制：只有 case-1 engine 才在当前 strong-resume / strong-continuity 支持范围内。

**FR-2: Case-1 engine 定义必须明确且可验证**
case-1 engine 必须同时满足：
1. **Phase-1 bootstrap** 能拿到 newly-created session 的 authoritative resume identifier
2. **Phase-2 continue** 能基于该 identifier 稳定继续同一个 session / conversation

**FR-3: 非-OpenClaw engine 必须经过两段式验证协议**
对于所有非-OpenClaw engine，系统必须采用两段式协议：
- **Phase 1**：建立最小 session，并获取 authoritative resume id
- **Phase 2**：基于该 id 继续真实任务

**FR-4: OpenClaw native path 视为既有 case-1 baseline**
OpenClaw native session model 已有显式 `session-id` continuity contract，因此本 PRD 不要求把 OpenClaw 也改造成两段式；它作为现有 case-1 baseline 保留。

**FR-5: Bootstrap 失败即 strong continuity 启动失败**
如果 Phase 1 无法获取 authoritative resume id，则该次 engine 启动必须被视为 strong continuity failure，而不是静默退化为 heuristic binding。

**FR-6: Heuristic discovery 不得作为 correctness foundation**
以下策略均不得被当作 strong continuity 的 correctness foundation：
- `--list-sessions` 文本解析
- prompt preview substring 匹配
- `latest` 推断
- index 推断
- 时间窗口推断
- 任何 post-hoc session 猜测逻辑

**FR-7: Heuristic discovery 可以保留为非 authoritative 辅助层**
上述 discovery/matching 策略可以存在，但只能用于：
- debugging
- observability
- explicit best-effort fallback
- manual investigation
不得被提升为“强正确性 continuity 证明”。

**FR-8: Bootstrap prompt 必须极薄**
Phase 1 的 bootstrap 必须是 ultra-thin prompt，不承载真实业务任务，不注入完整执行契约，不让 agent 在这个阶段开始真正工作。

**FR-9: Phase-2 必须保留完整主任务 envelope**
现有 role declaration、reference index、execution contract、final checklist 等主任务 envelope 必须集中保留在 Phase 2，以避免 bootstrap 污染主任务注意力。

**FR-10: Bootstrap result 必须持久化为 machine-readable artifact**
每次非-OpenClaw engine 的 Phase-1 bootstrap 都必须写出一个 machine-readable bootstrap result artifact，供 runtime 在进入 Phase 2 前做硬判断。

**FR-11: Bootstrap artifact 必须是 invocation-scoped，而不是 run-level 单文件**
系统不得把所有 agent / retry / phase 的 bootstrap 结果混写到同一个共享文件中。
每次 bootstrap 必须生成独立 artifact，并通过固定 index / pointer 机制暴露当前 active bootstrap 结果。

**FR-12: Strong continuity eligibility 必须基于 bootstrap result 决定**
runtime 不得根据 CLI stdout 文本的非结构化启发式结果直接判断 engine 已满足 case-1；必须依据 bootstrap result artifact 的 authoritative 字段做决定。

**FR-13: 两段式 bootstrap 必须挂在 continuity mode flag 后面**
该设计属于高影响 runtime 行为变更，必须通过明确的 continuity mode 开关控制。
至少应支持：
- `legacy`
- `case1_strict`

**FR-14: `legacy` 与 `case1_strict` 必须有清晰语义边界**
- `legacy`：保留当前旧的 continuity / discovery 路径
- `case1_strict`：启用 case-1 gating、两段式 bootstrap，以及 fail-closed strong continuity 判断

### Non-Functional Requirements

**NFR-1: Honesty over fake support**
宁可明确声明某 engine 暂不支持 strong continuity，也不要建立在 heuristic identity binding 上假装支持。

**NFR-2: Bounded scope**
本 PRD 不授权一次性重写全部多引擎 runtime，只定义：
- 当前支持边界
- case-1 判断标准
- 两段式 bootstrap protocol
- prompt / envelope 保护原则

**NFR-3: Prompt-strength preservation**
两段式设计不得显著削弱 coder / planner / reviewer / verifier 等角色在真实任务阶段的注意力强度与执行质量。

### User Stories

- 作为 operator，我希望只有在 engine 真正满足强 continuity 条件时，系统才宣称支持 resume correctness。
- 作为 operator，我希望 bootstrap 如果拿不到 authoritative id，就立即失败，而不是事后靠猜测拼 continuity。
- 作为 operator，我希望 Phase 1 只是建立会话，不污染真正任务的主提示词。
- 作为 architect，我希望 runtime-owned truth 与 provider-owned resume handle 的边界被明确建模，而不是混在一起。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
> **[Instruction to Main Agent/Architect]** Write down the technical decisions made during the co-pilot discussion. Which existing files/modules are targeted? What design patterns or architectural trade-offs were chosen?

### Core design principle

> **Strong continuity requires authoritative bootstrap-time identity, not post-hoc guesswork.**

### 3.1 Support boundary: case-1 only

当前 `leio-sdlc` strong continuity 支持边界应明确为：

- **支持**：case-1 engine
- **不支持**：无法提供 bootstrap-time authoritative resume-id acquisition 的 engine

这条规则优先于“多引擎覆盖率”。

### 3.2 Two-phase protocol for non-OpenClaw engines

#### Phase 1 — Bootstrap
目的：
- 建立一个最小 session
- 获取 authoritative resume identifier
- 将该 identifier 写入 runtime-owned state
- 生成 bootstrap result artifact 供 runtime 判定是否进入 Phase 2

要求：
- identifier 必须来自 authoritative CLI/runtime source
- 不能只依赖 model free-text output
- Phase 1 不承载真实业务任务
- 若没有 authoritative id，则必须显式标记 bootstrap failed

#### Phase 2 — Continue
目的：
- 使用 Phase 1 获得的 authoritative id 继续真正任务
- 将完整主任务 envelope 注入到这次 continuation 中

要求：
- engine 必须能够可靠地基于该 id 继续同一个 session/conversation
- 若失败，则表明该 engine 不满足 case-1 强 continuity 要求

### 3.3 Continuity mode flag and rollout strategy

由于两段式 bootstrap 会改变 agent 启动语义、failure mode 与 prompt 时序，本 PRD 要求该设计必须挂在明确的 mode flag 后面。

推荐的 continuity mode 为：

```text
legacy
case1_strict
```

语义如下：
- `legacy`：保留当前旧的 continuity / discovery 行为，作为回滚与行为对照基线
- `case1_strict`：启用 case-1 engine gating、两段式 bootstrap、bootstrap artifact hard gate，以及 fail-closed strong continuity 规则

上线策略应为：
1. 初期默认保持 `legacy`
2. 在受控范围内灰度验证 `case1_strict`
3. 只有在行为与质量信号稳定后，才考虑扩大启用范围

### 3.4 Authoritative-source rule

本 PRD 对“authoritative source”做出硬定义：

可被视为 authoritative 的 resume identifier 来源仅限于：
1. CLI/runtime 直接返回的 machine-readable metadata 字段
2. provider-documented 且当前版本 live-verified 的 direct resume handle
3. runtime 在 bootstrap 阶段直接捕获并写入的结构化结果

以下来源 **不得** 视为 authoritative：
- model 自由文本中“自报”的 session / conversation id
- 从 session list 文本中反向推测出的候选 id
- `latest` / index / 时间窗口 / prompt preview 匹配得到的结果
- 任何未经过结构化 contract 验证的后验猜测

### 3.5 Bootstrap artifact location model

bootstrap artifact 必须与当前 SDLC run 的其它 authoritative artifacts 一起放在 `run_dir` 下，但不能使用 run-level 单文件名，否则不同 agent / retry / phase 会相互覆盖或混淆。

因此本 PRD 要求：

1. bootstrap artifacts 根目录必须为：

```text
<run_dir>/bootstrap/
```

2. 每次 bootstrap 必须生成 invocation-scoped artifact：

```text
<run_dir>/bootstrap/<agent_invocation_id>.json
```

3. runtime 若需要读取“当前 active bootstrap 结果”，必须通过固定 index / pointer artifact，而不是扫描目录做启发式猜测。

推荐的固定 index artifact 为：

```text
<run_dir>/bootstrap_index.json
```

该 index 用于把逻辑上的 active agent/bootstrap target 映射到具体 artifact 路径。

### 3.6 Bootstrap result contract

为避免“原则对了但 runtime 无法硬判断”，非-OpenClaw engine 的 Phase-1 必须产出 bootstrap result artifact。

每个 bootstrap result artifact 的路径必须遵循：

```text
<run_dir>/bootstrap/<agent_invocation_id>.json
```

其最小 required schema 应为：

```json
{
  "engine": "string",
  "ok": true,
  "phase": "bootstrap",
  "authoritative": true,
  "resume_handle": "string",
  "resume_kind": "session_id|conversation_id|provider_handle",
  "source": "cli_runtime",
  "captured_at": "ISO-8601 string"
}
```

若 bootstrap 失败，则必须写出 machine-readable failed result，而不是只打日志，例如：

```json
{
  "engine": "string",
  "ok": false,
  "phase": "bootstrap",
  "authoritative": false,
  "resume_handle": null,
  "failure_reason": "missing_authoritative_resume_handle"
}
```

runtime 是否允许进入 Phase 2，必须只基于该 artifact 做硬判断。

固定 index artifact 的最小 required shape 应为：

```json
{
  "active_targets": {
    "<logical_target>": "bootstrap/<agent_invocation_id>.json"
  }
}
```

### 3.7 Runtime-owned truth vs provider-owned handle

必须显式区分两类 identity：

1. **Runtime-owned identity**
   - `run_id`
   - `session_key`
   - `agent_invocation_id`
   - `prompt_path`
   - `workdir`
   - timestamp
   - engine/model metadata

2. **Provider-owned handle**
   - provider session id
   - conversation id
   - resume token
   - 或其它 provider-native resume handle

只有当 provider-owned handle 在 bootstrap 阶段被 authoritative 获取时，strong continuity 才成立。

### 3.8 Gemini implication

Gemini 是本 PRD 的 motivating case。

当前 live evidence 说明：
- Gemini 有 resume 能力
- 但当前并未证明 `leio-sdlc` 已具备一个 **bootstrap-time authoritative session-id acquisition path**

因此在该协议被证明前，Gemini 不应被视为已验证的 case-1 engine。

### 3.9 Prompt / envelope protection strategy

当前 prompt 构造路径较重：
- role prologue
- reference index
- execution contract
- final checklist
- prompt file indirection (`Read your complete task instructions from <path> ...`)

这意味着如果把 bootstrap 指令混进现有主任务 envelope，会显著增加注意力涣散风险。

因此本次明确选择以下 trade-off：

- **Do not** 把 bootstrap 指令直接塞进现有 Phase-2 主任务 envelope
- **Do** 把 Phase 1 做成单独、极薄的 bootstrap step
- **Do** 在 Phase 2 保留现有主任务 envelope 的完整强度

### Target modules / files
以下文件被明确授权纳入本次设计/实现范围：
- `scripts/agent_driver.py`
- `scripts/envelope_assembler.py`
- 相关 spawn / orchestration 接线文件（如确有需要）
- Gemini / engine capability 相关测试文件

## 4. Acceptance Criteria (BDD 黑盒验收标准)
> **[Instruction to Main Agent]** Use BDD format (Given/When/Then) to define the black-box behavior requirements. Do NOT write granular automated unit tests here. The downstream Planner will use this + Test Strategy to generate the exact TDD implementation blueprint.

- **Scenario 1: Unsupported engine is rejected for strong continuity**
  - **Given** an engine that cannot provide authoritative bootstrap-time resume-id acquisition
  - **When** SDLC strong continuity is requested
  - **Then** the runtime rejects that engine as out of current support scope

- **Scenario 2: Bootstrap obtains authoritative identifier**
  - **Given** a case-1-capable engine
  - **When** Phase 1 bootstrap runs
  - **Then** the runtime records an authoritative resume identifier for the newly created session
  - **And** writes a machine-readable bootstrap result artifact with `ok=true` and `authoritative=true`

- **Scenario 3: Continue phase resumes the same session**
  - **Given** a successful Phase 1 bootstrap with a valid authoritative resume identifier
  - **When** Phase 2 begins
  - **Then** the engine continues from that exact identifier rather than starting a fresh unrelated session

- **Scenario 4: Bootstrap failure aborts strong continuity path**
  - **Given** a non-OpenClaw engine whose Phase 1 bootstrap cannot obtain an authoritative resume identifier
  - **When** the runtime attempts strong continuity startup
  - **Then** the runtime writes a machine-readable failed bootstrap result
  - **And** treats that as startup failure for strong continuity rather than silently falling back to heuristic session matching

- **Scenario 5: Heuristic discovery is not upgraded into proof**
  - **Given** a text-parsed or otherwise heuristically matched session candidate
  - **When** the runtime has no authoritative bootstrap-time identity binding
  - **Then** the runtime must not treat that candidate as proof of strong continuity correctness

- **Scenario 6: Phase-2 prompt strength is preserved**
  - **Given** a two-phase engine startup design
  - **When** the real task is executed in Phase 2
  - **Then** the full role/task envelope remains concentrated in Phase 2 and is not materially weakened by bootstrap instructions

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
> **[Instruction to Main Agent/Architect]** Define HOW this feature must be verified at a macro level.
> - What is the core quality risk?
> - Should we use Mocking? Which dependencies must be mocked?
> - Do we need E2E sandboxed tests or just unit tests?
[Your strategic testing guidance goes here]

### Core quality risks
1. 系统继续偷偷把 heuristic discovery 当作 strong continuity proof
2. Phase 1 虽然存在，但拿到的并非 authoritative id
3. Phase 2 的完整主任务 envelope 被 bootstrap 污染，导致 agent 能力弱化
4. runtime-owned truth 与 provider-owned handle 边界继续混淆

### Strategic verification guidance
1. **Capability classification tests are mandatory**
   - 必须验证 engine 是否满足 case-1 判定条件
2. **Bootstrap success/failure classification tests are mandatory**
   - 拿不到 authoritative id 时必须 fail closed for strong continuity
   - bootstrap result artifact 的 success / failure schema 必须被验证
3. **Heuristic non-upgrade tests are mandatory**
   - 必须验证 text parsing / latest / preview match 不会被偷偷升级为强正确性证明
4. **Prompt-strength preservation review is mandatory**
   - 必须验证 Phase 2 仍然保留当前主要 execution envelope 的完整性
5. **Prefer sandboxed / mocked validation for bootstrap contract**
   - 先做 deterministic contract tests
   - live Gemini smoke 可作为补充验证，但不是唯一质量门
6. **OpenClaw regression tests are mandatory**
   - 必须验证本 PRD 引入的 case-1 gating / bootstrap path 不会破坏现有 OpenClaw native continuity baseline
7. **Mode-gated rollout tests are mandatory**
   - 必须验证 `legacy` 与 `case1_strict` 两种模式在 runtime 分支上可被清晰区分
   - 必须验证关闭 `case1_strict` 时可以恢复旧行为

### Quality goal
本项目质量目标不是“尽量支持更多 engine 名义 resume”，而是：
- 只对满足 case-1 的 engine 提供强 continuity 承诺
- 对不满足条件的 engine 诚实拒绝
- 保护主任务 prompt 强度不被 bootstrap 稀释

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/envelope_assembler.py`
- `scripts/orchestrator.py`
- `scripts/config.py`（如 continuity mode flag 通过配置接入）
- 相关 Gemini / engine capability 测试文件
- 如确有必要，相关 spawn / orchestration 接线文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial framing focused too narrowly on whether `gemini --list-sessions -o json` returned machine-readable JSON.
- **Audit Rejection (v1.0)**: That framing was too shallow because the real correctness question is bootstrap-time authoritative identity, not merely text-vs-JSON parsing.
- **v2.0 Revision Rationale**: The design was tightened to case-1-only engine support, a two-phase bootstrap/continue protocol, and explicit protection of Phase-2 prompt strength.

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact support rule
```text
Only case-1 engines are in scope for strong continuity support.
```

### Exact case-1 definition
```text
A case-1 engine must support authoritative bootstrap-time resume-id acquisition and reliable resume by that identifier.
```

### Exact continuity modes
```text
legacy
case1_strict
```

### Exact two-phase labels
```text
Phase 1: bootstrap
Phase 2: continue
```

### Exact bootstrap artifact directory rule
```text
<run_dir>/bootstrap/
```

### Exact bootstrap artifact path rule
```text
<run_dir>/bootstrap/<agent_invocation_id>.json
```

### Exact bootstrap index artifact path rule
```text
<run_dir>/bootstrap_index.json
```

### Exact bootstrap success artifact
```json
{
  "engine": "string",
  "ok": true,
  "phase": "bootstrap",
  "authoritative": true,
  "resume_handle": "string",
  "resume_kind": "session_id|conversation_id|provider_handle",
  "source": "cli_runtime",
  "captured_at": "ISO-8601 string"
}
```

### Exact bootstrap failure artifact
```json
{
  "engine": "string",
  "ok": false,
  "phase": "bootstrap",
  "authoritative": false,
  "resume_handle": null,
  "failure_reason": "missing_authoritative_resume_handle"
}
```

### Exact bootstrap index artifact
```json
{
  "active_targets": {
    "<logical_target>": "bootstrap/<agent_invocation_id>.json"
  }
}
```
