---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Reviewer and Verifier Evidence-Only Evaluation Boundary

## 1. Context & Problem (业务背景与核心痛点)
当前 `leio-sdlc` 的 reviewer 与 verifier / UAT verifier 在职责边界上存在一个重复出现的风险：它们本应是**静态 / 证据型评估角色**，但在真实运行中可能自行滑向“动态测试执行者”。

这已经在 reviewer 路径上真实发生过。reviewer 在正确读取 PRD、PR contract、diff 之后，进一步自行执行了：

```sh
bash scripts/test_missing_channel.sh && bash scripts/test_missing_force_replan.sh && bash scripts/test_orchestrator_logs.sh
```

结果不是帮助流程，而是：
- 触发了 approval request；
- 让 review phase 卡在错误的执行路径上；
- 使 review report 停留在 `NOT_STARTED`；
- 最终让 SDLC 因“错误的失败原因”中断。

这个问题不应被视为 reviewer-only 偶发 glitch，因为 verifier / UAT verifier 也存在同型风险：
- verifier 本应评估 acceptance / verification evidence；
- 如果 verifier 也开始自行执行 repo tests 或 approval-requiring commands，角色边界就会用同样方式塌陷。

本问题的本质不是“某个模型不够聪明”，而是 **reviewer / verifier 的 role contract 不够硬**：
- coder 负责实现和执行需要的验证；
- reviewer 负责读 PRD / PR contract / diff / coder evidence，并给出 structured review；
- verifier 负责读 acceptance surface、UAT/verification evidence、以及必要的产物，并给出 structured verdict；
- orchestrator 负责安排什么时候跑动态执行、什么时候进入 review/UAT。

如果 reviewer / verifier 自己也去执行 repo validation，就会产生这些结构性问题：
- 审核/验收阶段可能死锁在 approval 上；
- 证据边界被评估者自己重新定义；
- orchestrator 不再是唯一的动态执行编排者；
- 流程错误会以 `NOT_STARTED`、missing artifact、approval deadlock 等伪症状暴露，而不是以真实的实现/验证缺口暴露。

本 PRD 的目标是恢复一个**轻量但硬边界**的 contract：
- reviewer 与 verifier 默认是 evidence-only evaluators；
- 不自行执行 repo tests；
- 不触发 approval-requiring commands；
- 当 evidence 不足时，报告“不足”，而不是越权执行；
- 用短、硬、不会稀释主任务语义的约束来实现这一点。

本 PRD **不处理**：
- 全局工具权限系统 / 平台级 tool sandbox；
- coder 的执行职责重定义；
- orchestrator 整体状态机重构；
- verifier / reviewer 以外角色的广义行为治理工程；
- GitHub integration。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须冻结 reviewer 的 evidence-only contract**
   - reviewer 必须以以下输入为评估依据：
     - PRD
     - PR contract
     - diff
     - coder-provided validation evidence
     - 已生成的相关 artifact / log
   - reviewer 不得自行执行 repo tests 或 approval-requiring commands 作为普通 review 的一部分。

2. **必须冻结 verifier / UAT verifier 的 evidence-only contract**
   - verifier 必须以以下输入为评估依据：
     - acceptance criteria
     - orchestrator / coder / pipeline 已生成的验证 evidence
     - UAT / verification artifacts
     - 必要的产物与日志
   - verifier 不得在普通 verification / UAT 过程中自行执行 repo tests 或 approval-requiring commands。

3. **当 evidence 不足时，reviewer / verifier 必须报告不足，而不是自执行**
   - 如果 reviewer 或 verifier 判断现有证据不足以给出高置信 verdict：
     - 必须在结构化输出中写明 evidence insufficient / evidence gap；
     - 不得因此自行启动 repo validation。

4. **必须保留 orchestrator 作为动态执行步骤的编排者**
   - 动态验证何时发生、由谁执行、执行哪些命令，必须继续由 orchestrator / coder / designated execution step 决定；
   - reviewer / verifier 不得把自己变成第二执行引擎。

5. **约束文本必须短、硬、不可歧义**
   - 不允许通过大段政策墙追加 prompt 来“解释很多原则”；
   - 必须使用简短、明确、不会冲淡主任务的规则表达：
     - 不跑 repo tests
     - 不触发 approval-requiring commands
     - evidence 不足则报告不足

6. **修复范围必须同时覆盖 reviewer 与 verifier**
   - 不允许只修 reviewer，而让 verifier 继续保留同型越权行为风险；
   - 但也不允许把范围膨胀到所有 agent role 的统一行为宪法。

### Non-Functional Requirements

1. **本 PRD 必须保持小边界**
   - 不做大型 runtime capability framework；
   - 不做通用工具权限平台重构；
   - 只修 reviewer / verifier 的普通 review/UAT 行为边界。

2. **实现方式必须避免 prompt 稀释主任务**
   - reviewer / verifier 的 guardrail 语言要精简；
   - 不能因为追加长篇限制而让模型偏离其核心评估任务。

3. **contract 必须在角色入口的真实提示链上生效**
   - 不能只改 issue 文案或外部说明；
   - 必须体现在 playbook / envelope / invocation chain 的真实输入中。

### User Stories

- **As an operator**, I want reviewer and verifier to stay in evidence-evaluation mode, so the pipeline no longer deadlocks because an evaluation role self-initiated approval-requiring execution.
- **As a maintainer**, I want insufficient evidence to be surfaced as a finding rather than silently converted into ad-hoc test execution, so failures remain attributable to the correct phase.
- **As a reviewer of the framework**, I want the fix to be narrow and lightweight, so we restore role boundaries without introducing a heavy global tool-permission platform.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **role-contract tightening with minimal semantic load** 路线：
- 不做大平台；
- 不做复杂权限系统；
- 直接把 reviewer / verifier 的行为边界写入它们真正会看到的 contract surfaces；
- 再用测试证明边界生效且不会稀释主任务。

### 3.1 冻结的 authoritative contract

#### A. Reviewer contract
reviewer 是 **evidence-based code evaluator**，不是 test runner。

reviewer 的正常职责：
- 读 PRD / PR contract / diff / coder evidence
- 评估正确性、计划对齐、证据充分性
- 写 structured review report

reviewer 的明确禁区：
- 不运行 repository tests
- 不触发 approval-requiring commands
- 不替 orchestrator/coder 做动态验证

#### B. Verifier contract
verifier / UAT verifier 是 **evidence-based acceptance evaluator**，不是 test runner。

verifier 的正常职责：
- 读 acceptance criteria / verification evidence / produced artifacts
- 判断是否满足验收与验证要求
- 写 structured verifier/UAT verdict

verifier 的明确禁区：
- 不运行 repository tests
- 不触发 approval-requiring commands
- 不替 orchestrator/coder 做动态验证

#### C. Insufficient-evidence fallback
对 reviewer 与 verifier，统一 fallback 必须是：
```text
If evidence is insufficient, report insufficient evidence instead of executing tests yourself.
```

#### D. Lightweight expression rule
这些边界必须以**极短、极硬、不可歧义**的方式表达；
不能以长篇政策墙形式追加，以免稀释 reviewer/verifier 主任务语义。

### 3.2 具体改动方向

#### A. `playbooks/reviewer_playbook.md`
必须加入 reviewer role-boundary 约束，且要短、硬：
- do not run repository tests
- do not trigger approval-requiring commands
- if evidence is insufficient, report insufficient evidence instead of executing tests yourself

#### B. verifier 相关 playbook / prompt surface
需要找到 verifier / UAT verifier 的真实 prompt/playbook 输入面，并加上与 reviewer 对称的短约束：
- do not run repository tests
- do not trigger approval-requiring commands
- if evidence is insufficient, report insufficient evidence instead of executing tests yourself

如果 verifier 当前没有独立 playbook，而是通过 envelope / invocation contract 组装，也必须在真实输入面中补上，而不是只写在 PM 说明里。

#### C. envelope / invocation chain
reviewer 与 verifier 的 execution contract / final checklist / invocation-time guardrail 中，必须包含上述短约束。

要求：
- reviewer 和 verifier 至少各有一处“真实会送到 agent 的 contract surface”明确包含这三条边界；
- 语言必须精简，不得扩写成大段 constitution。

#### D. 明确不采用的方案
本 PRD 不采用：
1. **只改 issue 文案，不改真实 prompt/playbook surface**
2. **只靠长篇追加 prompt 试图压住模型行为**
3. **直接上全局工具权限系统 / reviewer-only tool sandbox 平台**
4. **把 reviewer / verifier / 所有角色统一塞进一个大而空的行为宪法**

### 3.3 Why this is enough for #31
issue #31 当前要解决的是：
- reviewer 已经真实越权执行 repo tests；
- verifier 也有同型风险；
- 造成 approval deadlock / report not started / phase attribution 错乱。

因此这次只需要做到：
- reviewer / verifier contract 收紧；
- evidence insufficient 变成明确 fallback；
- 短语义 guardrail 生效；
- 回归测试防止 drift。

不需要在这一轮内解决：
- 全局 tool permissions
- orchestrator 大重构
- 所有角色统一治理

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: reviewer remains evidence-only during ordinary review**
  - **Given** a normal reviewer run with PRD, PR contract, diff, and coder-provided evidence
  - **When** reviewer is invoked for ordinary code review
  - **Then** reviewer evaluates based on those inputs and writes a structured review artifact
  - **And** reviewer does not self-initiate repository test execution as part of the ordinary review flow

- **Scenario 2: verifier remains evidence-only during ordinary verification/UAT**
  - **Given** a normal verifier/UAT run with acceptance criteria, produced artifacts, and pipeline-generated verification evidence
  - **When** verifier is invoked for ordinary verification/UAT
  - **Then** verifier evaluates based on those inputs and writes a structured verdict artifact
  - **And** verifier does not self-initiate repository test execution as part of the ordinary verification flow

- **Scenario 3: insufficient evidence is reported, not converted into self-execution**
  - **Given** reviewer or verifier determines that the provided evidence is insufficient for a confident verdict
  - **When** the role completes its evaluation step
  - **Then** the resulting artifact records insufficient evidence / evidence gap
  - **And** the role does not attempt to execute repo validation on its own

- **Scenario 4: ordinary review/UAT no longer triggers approval requests from evaluation roles**
  - **Given** a normal reviewer or verifier run
  - **When** the role performs its standard evaluation task
  - **Then** the flow does not produce approval requests caused by reviewer/verifier self-executing repo validation

- **Scenario 5: role-boundary guardrail is present in the real prompt/input surface without overwhelming the task**
  - **Given** the actual prompt / envelope / playbook surface delivered to reviewer or verifier
  - **When** that surface is inspected
  - **Then** it contains a short, explicit prohibition on self-executing repo tests and approval-requiring commands
  - **And** it contains the short fallback instruction to report insufficient evidence instead of self-executing tests
  - **And** it does not introduce a long policy wall that materially dilutes the role’s primary evaluation task

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是单点代码 bug，而是 **评估角色与执行角色之间的职责边界继续漂移**：
- reviewer/verifier 觉得“为了更有把握，自己跑一下”；
- 结果把评估步骤变成执行步骤；
- 最终在错误阶段触发 approval deadlock 或伪失败。

### 推荐测试策略

1. **优先做 prompt/envelope contract tests**
   - 验证 reviewer 和 verifier 的真实输入面包含精简、明确的边界约束；
   - 这类测试是防 drift 的第一层。

2. **做 ordinary-flow regression tests**
   - 验证普通 review / UAT 路径不会因为评估角色自执行 repo validation 而走向 approval request 或 `NOT_STARTED` 伪失败形态。

3. **适度 mock，避免重型 E2E**
   - 可以 mock 外部 agent 输出与握手；
   - 重点验证 contract surface、artifact outcome、以及错误形态是否消失；
   - 不需要把本 PRD 膨胀成全套 tool-permission E2E 平台测试。

4. **验证短提示不会稀释主任务**
   - 应通过 prompt inspection / focused tests 证明：边界约束存在，但没有变成长篇政策墙。

### Quality Goal
修复完成后，`leio-sdlc` 必须满足：
- reviewer 与 verifier 默认保持 evidence-only evaluator 角色；
- ordinary review/UAT 不再因评估角色自执行 repo validation 而触发 approval deadlock；
- evidence insufficiency 被正确报告，而不是被偷偷转换成越权执行；
- 边界约束短、硬、稳定，不稀释主任务。

## 6. Framework Modifications (框架防篡改声明)
- `playbooks/reviewer_playbook.md`
- verifier / UAT verifier 对应的真实 prompt / playbook / envelope 输入面
- `scripts/envelope_assembler.py`（如果 reviewer/verifier contract 通过此处进入真实输入面）
- `scripts/spawn_reviewer.py`
- verifier 对应入口文件（如果 verifier contract 通过该入口注入）
- 与 reviewer/verifier evidence-only contract 直接相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 reviewer-only 问题边界扩大为 reviewer + verifier 的 evidence-only evaluation boundary，同时明确 guardrail 语言必须短、硬、不可稀释主任务。
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
- **`evaluation_role_boundary_rule_1`**:
```text
Do not run repository tests.
```

- **`evaluation_role_boundary_rule_2`**:
```text
Do not trigger approval-requiring commands.
```

- **`evaluation_role_boundary_fallback`**:
```text
If evidence is insufficient, report insufficient evidence instead of executing tests yourself.
```
