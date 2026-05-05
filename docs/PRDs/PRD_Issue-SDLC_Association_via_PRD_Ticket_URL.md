---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue-SDLC Association via PRD Ticket URL

## 1. Context & Problem (业务背景与核心痛点)
当前 leio-sdlc 的上游 PM/PRD 流程、下游 SDLC 执行流程，以及 GitHub Issue / Pull Request / CI/CD 之间没有清晰的接口定义。

现状存在三个核心问题：

1. **PRD 与来源需求缺少稳定关联**
   - 用户可能先在 GitHub Issue 中提出需求或缺陷，再进入共创讨论与 PRD 编写。
   - 但当前 PRD 文档本身无法稳定表达“这个 PRD 来源于哪个 issue / ticket”。
   - 这导致后续 PRD 审核通过、SDLC 执行完成、Pull Request 创建时，都需要人工重新寻找来源上下文。

2. **PRD baseline / commit 时机耦合在 SDLC 启动阶段**
   - 当前流程中，PRD 通过 Auditor 后，并不在 PM 流程中自然收尾。
   - 相反，PRD 的 baseline 动作被耦合到了 SDLC 启动前的 `commit_state.py` 提示路径上。
   - 这使得 PM → SDLC 的交接接口不清晰：SDLC 启动时还要承担一部分上游产物收尾责任。
   - 同时，当前流程也没有定义 PRD 过审后如何把 baseline 结果（尤其是 commit hash）回写到来源 issue，导致审计通过与仓库状态之间缺少可验证连接。

3. **Issue 与 SDLC 的整合容易被过度设计**
   - SDLC 内部的 Planner / Coder / Reviewer / Verifier 并不需要知道 issue 编号，也不应被 GitHub 特性污染。
   - 真正需要的是一个轻量、通用、低耦合的关联方式，使 Agent 能在需要时从 PRD 追溯到来源 ticket。

本 PRD 的目标不是实现 GitHub 自动化编排，也不是让 orchestrator 直接管理 issue，而是先建立一个足够清晰、足够稳定的最小接口：

- PRD 可选携带一个 `Primary_Issue` URL 和 0 到若干个 `Related_Issues` URL
- PM 流程在 PRD 过审后完成 baseline / commit
- SDLC 只接收“已 commit 的 PRD”作为输入
- Agent 在后续需要更新 issue 或创建 PR 时，可通过读取 PRD 中的 issue-tracking 字段完成手动 GitHub 操作

这为后续 GitHub PR、Review、CI/CD 的更深层整合提供了低风险的演进基础。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **PRD 模板必须新增可选的 issue-tracking frontmatter 字段**
   - 目标修改文件（源码唯一真源）为：
     - `leio-sdlc/skills/pm-skill/TEMPLATES/PRD.md.template`
   - 模板必须支持并默认写死为：
     - `Primary_Issue: ""`（始终存在，默认空字符串）
     - `Related_Issues: []`（始终存在，默认空列表）
   - 这些字段必须是 URL 列表语义的承载位，但默认值必须是 YAML 安全且可机器解析的确定值，而不是占位符示意。
   - 这样既保留 tracker-agnostic 能力，又避免 schema 漂移和空值歧义。

2. **SDLC 内部执行组件不得依赖 issue-tracking 字段**
   - Planner / Coder / Reviewer / Verifier 的行为不得因为 PRD 中存在或不存在 `Primary_Issue` / `Related_Issues` 字段而变化。
   - 这些字段只是一条追溯链路，不得成为执行语义的一部分。

3. **PRD baseline 的责任必须从 SDLC 启动路径移回 PM 流程收尾阶段**
   - 当 PRD 通过 Auditor 审核后，PM 流程应将其视为正式交付物，并完成 baseline / commit。
   - SDLC 启动时仍保留“PRD 必须已 commit”的 guardrail，但不再承担指导用户补做 PM 收尾动作的职责。

4. **Orchestrator 的 pre-flight 错误文案必须更新**
   - 当检测到 PRD 尚未 baseline / commit 时，应明确提示“请先完成 PM / Auditor 阶段的 baseline / commit”，而不是让用户理解为“这是 SDLC 启动时的例行操作”。

5. **Agent 必须可以通过读取 PRD 中的 issue-tracking 字段执行后续 GitHub 手动动作**
   - 例如：PRD 过审后 comment 回主 issue、在相关 issue 上补充引用、SDLC 完成后创建 draft PR 并回贴链接。
   - `Primary_Issue` 用于定义该 PRD 对应的主要 issue / ticket。
   - `Related_Issues` 用于表达该 PRD 同时覆盖的其他相关 issue / ticket。
   - 本 PRD 不要求这些行为自动化，但要求该信息通道被打通。

6. **Auditor APPROVED 后，Agent 必须进入“等待收尾指令”的半自动模式**

6. **Auditor APPROVED 后，Agent 必须进入“等待收尾指令”的半自动模式**
   - Auditor 通过后，Agent 必须先报告 APPROVED，并停止自动推进。
   - Agent 不得在未获得进一步明确指令时自动执行 baseline commit 或自动更新 issue。
   - 用户可通过简短指令触发收尾动作，例如：`commit baseline` 或 `commit并更新issue`。

7. **当用户明确要求“commit并更新issue”时，Agent 必须执行完整收尾链路**
   - 调用 `commit_state.py --files <PRD>` baseline 该 PRD。
   - 获取 baseline commit hash。
   - 更新 `Primary_Issue`，内容至少包含：PRD 路径、baseline commit hash、PRD 已过审且可在明确授权后启动 SDLC。
   - 如存在 `Related_Issues`，应至少对其补充引用性更新。

### Non-Functional Requirements

1. **低耦合**：不得让 leio-sdlc 核心流程强依赖 GitHub。
2. **向后兼容**：没有 issue-tracking 字段的旧 PRD 仍应可被现有 SDLC 执行。
3. **低改动量**：本次应优先选择最小必要变更，不引入新的 adapter 层、状态机、后台同步逻辑。
4. **可演进**：未来如需自动更新 issue / 创建 PR / 驱动 CI/CD，应能基于这些 issue-tracking 字段继续扩展，而不是推翻本设计。

### User Stories

- **As a PM / Main Agent**, when I write a PRD for work that originated from one or more external issues, I want to record a primary issue URL and optional related issue URLs in the PRD so that the artifact remains traceable.
- **As a downstream SDLC operator**, when I start SDLC execution, I want the PRD to already be baseline-committed so that the PM/SDLC handoff is clean and explicit.
- **As an Agent handling PM-flow completion**, when the Auditor approves a PRD, I want to stop and wait for an explicit completion instruction before performing baseline commit or issue updates, so that repo/external side effects remain human-authorized.
- **As an Agent handling post-approval coordination**, when I am asked to baseline and update issues, I want to include the resulting commit hash in the issue update so that approval state is tied to a verifiable repository state.
- **As a framework maintainer**, I want this integration to remain tracker-agnostic and optional so that leio-sdlc can still run fully without GitHub.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用**最小接口设计**，将“Issue / Ticket 系统”与“SDLC 执行引擎”之间的交互压缩为一个单向、可选、文档级的元数据字段。

### 3.1 设计原则

1. **PRD 是交接物，不是运行时控制面**
   - PM 流程的产物是 PRD。
   - SDLC 的输入也是 PRD。
   - 因此，Issue / Ticket 与 SDLC 之间最稳定的接口应该写入 PRD，而不是依赖运行时参数或 chat 上下文。

2. **`Primary_Issue` + `Related_Issues` 优于单个 issue number**
   - 采用：
     - `Primary_Issue: ""`
     - `Related_Issues: []`
   - 这样避免把 GitHub 的编号模型写死到框架中。
   - 同时兼容“一个 PRD 覆盖多个 issue”的常见真实场景。
   - 并与现有 `Affected_Projects`、`Context_Workdir` 的 frontmatter 风格保持一致。

3. **Orchestrator 不直接管理 issue；Auditor 也不执行副作用**
   - orchestrator 仍然只做 PRD 合法性检查、切片、执行编排。
   - Auditor 只负责给出 APPROVED / REJECTED verdict，不直接产生 git commit 或外部 ticket 更新等副作用。
   - GitHub issue 的更新、PR 创建等动作由主 Agent 在流程边界读取 PRD 后手动完成。

4. **PM 流程负责 baseline，且以半自动 completion step 收尾；SDLC 流程负责执行**
   - PRD 一旦通过 Auditor，说明其已成为可执行的上游合同。
   - baseline / commit 应属于 PM 流程的收尾职责，而不应被延迟到 SDLC 启动时再补做。
   - 但该收尾步骤不应在 APPROVED 后自动发生，而应由 Agent 报告通过结果后，等待用户明确下达诸如“commit baseline”或“commit并更新issue”的指令再执行。

### 3.2 预期流程

#### 新流程

```text
需求 / 讨论
  →（可选）存在一个主 issue 与若干 related issues
  → PM skill 生成 PRD（若已知 issue，则写入 `Primary_Issue` / `Related_Issues`）
  → Auditor 审核
  → Auditor APPROVED 后，Agent 报告通过并暂停
  → 用户明确发出收尾指令（如：commit baseline / commit并更新issue）
  → Agent 执行 commit_state.py baseline PRD
  → Agent 获取 baseline commit hash
  →（可选）Agent 手动更新主 issue，并在相关 issue 上补充引用
  → PM 流程结束
  → SDLC 启动，读取已 commit 的 PRD
  → SDLC 完成
  →（可选）Agent 读取 PRD 中的 issue-tracking 字段，手动创建 PR / 更新 issue
```

#### 边界划分

- **PM 流程负责**
  - PRD 编写
  - Auditor 审核
  - Auditor APPROVED 后的 completion step
  - baseline / commit
  - （可选）PRD 审核通过后的 issue 通知

- **SDLC 流程负责**
  - 接收已 commit 的 PRD
  - 执行 planner/coder/reviewer/verifier 编排

- **主 Agent 负责**
  - 在流程边界读取 PRD 中的 `Primary_Issue` / `Related_Issues`
  - 在 APPROVED 后等待明确收尾指令
  - 收到指令后执行 baseline、收集 commit hash、更新 issue
  - 执行所有与 issue / PR / review 相关的手动 GitHub 操作

### 3.3 目标修改点

1. **PRD 模板**
   - 在 frontmatter 中新增以下可选字段：
     - `Primary_Issue`
     - `Related_Issues`
   - 目标模板文件至少包括：
     - `~/.openclaw/skills/pm-skill/TEMPLATES/PRD.md.template`
     - `~/.openclaw/skills/leio-sdlc/skills/pm-skill/TEMPLATES/PRD.md.template`（如仍为运行时有效副本则必须同步）
   - 默认值允许为空或为空列表，但字段结构必须存在于模板中。

2. **orchestrator.py**
   - 保留“未 baseline 的 PRD 禁止启动”的 pre-flight guardrail。
   - 调整错误文案，使其指向 PM 阶段职责，而不是暗示这一步属于 SDLC 启动流程的一部分。

3. **流程约定**
   - 明确 `commit_state.py` 仍是唯一正式 baseline 工具。
   - 其调用时机从“SDLC 启动前补做”迁移到“PRD 审核通过后的 PM completion step”。
   - 该 completion step 由 Agent 在获得明确用户指令后执行，不在 Auditor APPROVED 后自动触发。
   - 若执行了 issue 更新，更新内容应包含 baseline commit hash。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: PRD template exposes optional issue-tracking metadata**
  - **Given** a user is creating a PRD for work that originated from one or more external issues
  - **When** the PM flow initializes a new PRD from the standard template
  - **Then** the generated PRD frontmatter contains an optional `Primary_Issue` field and an optional `Related_Issues` field
  - **And** those fields accept full tracker URLs instead of GitHub-specific issue numbers

- **Scenario 2: Legacy PRDs still work**
  - **Given** an existing PRD that does not contain issue-tracking fields
  - **When** SDLC is launched against that PRD
  - **Then** the SDLC pipeline still behaves as before and does not fail because those fields are absent

- **Scenario 3: Agent pauses after approval**
  - **Given** a PRD has passed Auditor review but has not yet been baseline-committed
  - **When** the Agent reports the APPROVED verdict
  - **Then** the Agent does not automatically baseline or update issues
  - **And** the flow explicitly waits for a follow-up completion instruction before any repo or external side effect occurs

- **Scenario 4: Explicit completion instruction performs baseline and issue update**
  - **Given** a PRD contains a valid `Primary_Issue` URL and optional `Related_Issues` URLs
  - **And** the PRD has already been approved by the Auditor
  - **When** the user explicitly instructs the Agent to `commit baseline` or `commit并更新issue`
  - **Then** the Agent baselines the PRD through `commit_state.py`
  - **And** captures the resulting commit hash
  - **And** includes that commit hash when updating the primary issue

- **Scenario 5: Agent can recover issue context from the PRD**
  - **Given** a PRD contains a valid `Primary_Issue` URL and optional `Related_Issues` URLs
  - **When** an Agent needs to perform a follow-up GitHub action after PRD approval or after SDLC completion
  - **Then** the Agent can locate the main and related source issues directly from the PRD without requiring additional runtime state or chat reconstruction

- **Scenario 6: SDLC guardrail still blocks unbaselined PRDs**
  - **Given** a PRD has passed audit but the user has not yet triggered the completion step
  - **When** a user attempts to launch SDLC with that PRD
  - **Then** the orchestrator blocks execution and clearly indicates that baseline / commit must be completed as part of the PM/Auditor completion flow

- **Scenario 7: SDLC internals remain tracker-agnostic**
  - **Given** a PRD contains `Primary_Issue` and `Related_Issues` URLs
  - **When** Planner, Coder, Reviewer, or Verifier are spawned downstream
  - **Then** none of those components change their execution logic based on the existence of those fields

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是功能实现本身，而是**边界职责重新划分后引入隐性流程断裂**：
- PRD 模板是否真的新增并稳定保留了 `Primary_Issue` / `Related_Issues` 字段
- 如存在双模板副本，是否发生只改一处导致运行时模板不一致
- Agent 是否会在 Auditor APPROVED 后错误地自动执行 baseline 或外部更新，越过人类确认
- PM completion step 是否真的在收到明确指令后完成 baseline
- issue 更新是否包含可验证的 baseline commit hash
- orchestrator 的 guardrail 文案是否正确引导用户
- 新字段是否破坏旧 PRD 的兼容性

### Verification Strategy

1. **模板级验证**
   - 直接检查新生成的 PRD scaffold 是否包含 `Primary_Issue` 与 `Related_Issues` 字段。
   - 如运行时存在双模板副本，验证两个模板输出结构一致。
   - 验证无 issue、单个 issue、多个 issue 时文档结构均合法。

2. **向后兼容验证**
   - 使用旧 PRD 样本运行 orchestrator pre-flight。
   - 确认不会因为缺失 issue-tracking 字段而新增失败。

3. **PM completion step 验证**
   - 模拟 Auditor APPROVED 后的主 Agent 收尾阶段。
   - 验证 Agent 会先停止并等待明确指令。
   - 在收到 `commit baseline` 或 `commit并更新issue` 指令后，再执行 baseline。
   - 若存在 issue 更新，验证更新文案包含 baseline commit hash。

4. **Guardrail 文案验证**
   - 构造一个未 baseline 的 PRD。
   - 启动 orchestrator，验证其错误文案明确指向 PM/Auditor 收尾责任。

5. **流程级手工验证**
   - 手工走一遍：创建带 `Primary_Issue` / `Related_Issues` 的 PRD → Auditor approve → Agent 停下等待 → 下达 `commit并更新issue` → baseline → 获取 commit hash → 手动 gh issue comment。
   - 目标不是自动化，而是确认链路可用。

### Mocking / E2E Guidance
- 本 PRD **不要求**引入 GitHub API 自动化测试。
- 不要求真实创建 issue / PR 的集成测试。
- 重点在模板、文案、流程边界和兼容性。

### Quality Goal
交付一个**低耦合、低风险、可演进**的最小接口，使后续更深层的 GitHub 整合可以建立在稳定的 PRD issue-tracking 元数据之上，而不是继续依赖对话上下文或运行时传参。

## 6. Framework Modifications (框架防篡改声明)
- `leio-sdlc/skills/pm-skill/TEMPLATES/PRD.md.template`
- `leio-sdlc/scripts/orchestrator.py`（仅限 pre-flight guardrail 文案调整）
- `~/.openclaw/skills/pm-skill/SKILL.md`（如需要同步更新 PM completion 约定文案，但不作为源码改动要求）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初版将 GitHub issue 状态同步、label 状态机、orchestrator 参数传递等能力纳入 #2 范围。
- **Audit Rejection (conceptual, pre-write)**: 讨论后认为该范围过重，会把 GitHub 语义污染到 SDLC 内部，并造成过早自动化。
- **v2.0 Revision Rationale**: 将 #2 收缩为最小可交付接口：PRD 中新增通用 issue-tracking 字段，并将 PRD baseline 责任明确移回 PM/Auditor 收尾阶段。GitHub issue / PR 更新动作由 Agent 在流程边界手动执行。
- **v3.0 Revision Rationale**: 进一步澄清 Auditor 只审不执行副作用；APPROVED 后由 Agent 进入半自动 completion step，等待用户明确下达 `commit baseline` 或 `commit并更新issue` 指令，再执行 baseline 并用 commit hash 更新相关 issue。
- **v4.0 Revision Rationale**: 收缩模板作用域为源码唯一真源 `leio-sdlc/skills/pm-skill/TEMPLATES/PRD.md.template`，并将 frontmatter 默认值写死为 YAML 安全的确定形式：`Primary_Issue: ""`、`Related_Issues: []`。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`prd_frontmatter_primary_issue_field`**:
```text
Primary_Issue: ""
```

- **`prd_frontmatter_related_issues_field`**:
```text
Related_Issues: []
```

- **`agent_post_approval_wait_instruction`**:
```text
PRD approved. Awaiting explicit completion instruction. Say "commit baseline" or "commit并更新issue" to perform PM completion actions.
```

- **`issue_update_required_fields`**:
```text
Issue update must include:
- PRD path
- baseline commit hash
- confirmation that the PRD is approved and baselined
- statement that SDLC launch still requires explicit authorization
```

- **`orchestrator_uncommitted_prd_guidance`**:
```text
[FATAL] Workspace contains uncommitted PRD/state files. Complete the PM/Auditor baseline flow before starting SDLC.
```

- **`orchestrator_uncommitted_prd_jit_guidance`**:
```text
[JIT] Baseline the approved PRD through the official PM/Auditor completion flow, then retry SDLC launch.
```
