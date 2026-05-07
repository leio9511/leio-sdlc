---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Dual Mode Preflight for Agent Fail-Fast and CI Report-All

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 已经完成了 GitHub CI Phase 2 soft-gate 的接入：GitHub Actions 现在能够真实执行仓库级 `bash preflight.sh`，并把 clean runner 上的真实失败暴露出来。

这一步已经证明：

- GitHub Actions `Preflight` workflow 能够被识别并真实触发；
- workflow 执行的是仓库权威 gate `bash preflight.sh`，而不是一套散装近似命令；
- CI 红灯现在已经是 truthful red，而不是 fake green。

但当前 `preflight.sh` 仍然只有单一执行模式：**fail-fast**。

这对 agent-driven SDLC 循环是合理的，因为：
- 输出短；
- 第一个失败就能给 coder / reviewer 明确的局部行动点；
- token 成本和上下文体积更可控。

但在 GitHub CI / human stabilization 阶段，fail-fast 会显著降低效率：
- 每次真实 GitHub run 只能暴露第一个失败项；
- true-green 恢复需要一条一条地挖失败；
- Epic #8 的 failure audit / backlog formation 速度变慢；
- GitHub 作为“共享 failure surface”的价值被削弱。

因此，当前真正的痛点不是 gate 是否真实，而是：

> **同一套真实 preflight checks，需要同时服务两个消费者：agent loop 与 human/CI audit，但它们对“停止策略”的需求不同。**

本 PRD 的目标不是创造第二套 gate，也不是修改 preflight 的真实通过/失败语义，而是：

> **在保持 `bash preflight.sh` 作为唯一权威 gate、保持 truthful red/green 语义不变的前提下，为 `preflight.sh` 增加两种停止策略：默认 fail-fast，用于 agent / SDLC；可选 report-all，用于 GitHub CI / human audit。**

本 PRD 不覆盖：

- 把 GitHub CI 变成 required merge gate（那属于 Epic #8 后续硬化阶段）；
- 真实 preflight failure 的具体业务修复（例如某个具体脚本失败）；
- 新增第二套独立 CI 命令链；
- 用 report-all 伪装成功或改变 failure truthfulness；
- 对整套 preflight checks 做大规模重构到完全不同的测试框架。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须保留 `bash preflight.sh` 作为唯一权威 gate 入口**
   - 现有仓库和 GitHub workflow 都继续通过 `bash preflight.sh` 进入 preflight。
   - 不允许为 CI/human audit 另造一套与 preflight 脱钩的“report-only”命令链。

2. **必须支持两种停止策略**
   - 默认模式：fail-fast
   - 显式模式：report-all

3. **默认模式必须保持向后兼容**
   - `bash preflight.sh` 仍表示 fail-fast；
   - 对现有 SDLC / coder / reviewer / 本地开发者默认行为不做破坏性改变。

4. **report-all 必须通过显式 flag 触发**
   - 例如：
     - `bash preflight.sh --report-all`
   - 不允许隐式通过环境漂移、GitHub-only 分支、或魔法检测切换行为。

5. **两种模式必须运行同一套底层 checks**
   - report-all 不是“更宽松版本”；
   - fail-fast 与 report-all 的区别只能是停止策略不同，而不是检查集合不同。

6. **report-all 仍必须 truthful fail**
   - 只要任意 check 失败，最终退出码必须非 0；
   - 不允许因为继续执行了更多 checks，就把失败包装成 success。

7. **GitHub CI 应可切换为 report-all 模式**
   - 使 GitHub Actions 在 stabilization / true-green 恢复阶段能一次暴露更多 failure surface；
   - 同时本地 / agent loop 仍保留 fail-fast。

8. **report-all 应尽量提高 failure discovery density，但不强行要求无条件“全跑到底”**
   - 某些 checks 若被早期失败实质性阻断，可被标记为 blocked / skipped / not-run；
   - 但系统必须尽可能继续跑仍然有意义的后续 checks。

9. **输出必须对人和 agent 都可用**
   - fail-fast 模式输出保持短、聚焦；
   - report-all 模式要能在结尾明确列出失败摘要，便于 backlog formation。

### Non-Functional Requirements

1. **语义必须单一**
   - 整个仓库只有一个真实 preflight gate；
   - dual-mode 只能改变 stopping policy，不能制造第二套 gate。

2. **truthfulness 不得削弱**
   - 无论 fail-fast 还是 report-all，红灯都必须是真红灯；
   - 绝不允许 fake green。

3. **blast radius 必须最小化**
   - 优先在 `preflight.sh` 顶层 runner 层引入模式控制；
   - 不要求一次性重写每个子测试脚本的内部实现。

4. **report-all 不能破坏 agent loop 体验**
   - 默认仍为 fail-fast；
   - agent/coder/reviewer 不应因这个功能而被迫处理巨量输出。

### User Stories

- **As a maintainer**, I want GitHub CI to reveal more than one failing preflight item per run so I can build the true-green backlog faster.
- **As an SDLC operator**, I want agent-driven execution to remain fail-fast so coder loops stay short and actionable.
- **As a reviewer**, I want one gate with one truth model, not two different test worlds depending on execution surface.
- **As an architect**, I want report-all to increase observability without weakening the honesty of the gate.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **single-gate / dual-stopping-policy** 策略。

### 3.1 核心设计原则

1. **One gate, two stopping policies**
   - 仍然只有一个仓库级 gate：`bash preflight.sh`；
   - fail-fast 与 report-all 是同一 gate 的两种执行策略，而不是两套 gate。

2. **默认行为必须稳定**
   - 不改变现有无参数行为；
   - 现有调用方（本地开发、SDLC、reviewer）继续使用 fail-fast。

3. **report-all 是 human/CI-facing 观察增强，不是语义降级**
   - report-all 的目标是尽可能多地收集失败项；
   - 它不是为了让 CI 变绿，也不是为了隐藏失败。

4. **失败累积应在 preflight 顶层 orchestrator 层实现**
   - 优先改 `preflight.sh` 的 `run_test` / `run_test_argv` / 汇总逻辑；
   - 不要求每个子测试脚本都先支持自己的 report-all。

### 3.2 推荐实现路径

当前 `preflight.sh` 已具备统一顶层 runner：
- `run_test`
- `run_test_argv`
- `run_live_llm_test`

建议实现如下：

1. 新增模式参数解析：
   - 默认 `MODE=fail-fast`
   - 遇到 `--report-all` 时切换到 `MODE=report-all`

2. 新增失败累积容器：
   - 记录失败项描述（如 `Bash Test: scripts/test_missing_channel.sh`）
   - 可选记录 blocked/skipped 项

3. 将当前“失败即 `exit 1`”的逻辑改成：
   - fail-fast：保留立即退出；
   - report-all：记录失败并继续执行后续仍有意义的 checks。

4. 在脚本末尾统一输出汇总：
   - 所有失败项列表；
   - 如存在 quarantined ignores，仍输出 quarantine 提示；
   - 若任意失败存在，最终 `exit 1`。

### 3.3 GitHub Actions 对接策略

- 本地 / agent / SDLC：
  - 继续用 `bash preflight.sh`
- GitHub Actions `Preflight` workflow：
  - 改为调用：
    - `bash preflight.sh --report-all`

这样：
- agent loop 保持小而快；
- GitHub CI 提升 failure discovery density；
- 不引入第二套 gate。

### 3.4 关于 blocked / skipped 的边界

report-all 不应被理解为无脑“所有东西都跑到底”。

某些 checks 如果被前置失败实质性阻断（例如环境/bootstrap 层没立住），后续检查可能失去信息价值。这种情况下允许：
- 继续执行其他独立 checks；
- 将明显失去意义的后续项标记为 blocked/skipped/not-run；
- 但不得因为存在阻断项就把整体结果包装成 success。

### 3.5 允许修改的范围

本 PRD 允许修改：
- `/home/openclaw/projects/leio-sdlc/preflight.sh`
- `.github/workflows/preflight.yml`（仅为切换到 `--report-all` 或适配新模式所需的最小改动）
- 与 preflight mode contract 直接相关的最小测试文件

本 PRD 不授权：
- 新建另一套平行 preflight 入口；
- 将 CI 变成 required merge gate；
- 大规模重构所有脚本测试结构；
- 修改每个失败脚本的业务逻辑本身（除非为模式正确性所必需）。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Default preflight remains fail-fast**
  - **Given** the repository preflight entrypoint
  - **When** `bash preflight.sh` is executed without extra flags
  - **Then** preflight stops on the first failing check
  - **And** it exits non-zero if any check fails

- **Scenario 2: Report-all mode accumulates multiple failures**
  - **Given** a repository state with more than one failing preflight check
  - **When** `bash preflight.sh --report-all` is executed
  - **Then** preflight continues past the first failing item where later checks remain meaningful to run
  - **And** it reports multiple failures in the final output summary
  - **And** it exits non-zero

- **Scenario 3: Fail-fast and report-all use the same gate surface**
  - **Given** the same repository state
  - **When** preflight is run in fail-fast mode and report-all mode
  - **Then** both modes execute the same underlying preflight gate
  - **And** the difference is limited to stopping behavior and output aggregation

- **Scenario 4: GitHub CI can use report-all without changing truthfulness**
  - **Given** the GitHub Actions `Preflight` workflow
  - **When** the workflow is configured to invoke `bash preflight.sh --report-all`
  - **Then** GitHub CI can expose a larger failure surface in one run
  - **And** the workflow still fails if any preflight check fails

- **Scenario 5: Agent-facing execution remains compact and actionable**
  - **Given** the SDLC / coder / reviewer execution path
  - **When** they invoke the default preflight command
  - **Then** they still observe fail-fast behavior
  - **And** they are not forced into report-all verbosity by default

- **Scenario 6: Report-all does not become fake green**
  - **Given** a repository state with at least one failing check
  - **When** `bash preflight.sh --report-all` completes
  - **Then** the final exit status remains failure
  - **And** the output does not represent the run as successful

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
最大的风险不是“实现一个 flag 很难”，而是：

1. report-all 无意中变成“继续跑但最后也成功”的 fake green；
2. CI 使用了 report-all 后，agent loop 也被污染成冗长输出；
3. dual-mode 造成两套 checks 漂移；
4. 某些前置失败导致后续结果全是噪音，report-all 输出反而不可用。

### Verification Strategy

#### A. Local contract verification
需要本地测试验证：
- 默认模式仍 fail-fast；
- `--report-all` flag 被正确识别；
- 两种模式共享同一 preflight gate surface；
- report-all 失败后最终仍 exit non-zero。

推荐测试文件：
- `tests/test_preflight_dual_mode.py`
- 如需最小 shell 合同测试，可新增 `scripts/test_preflight_dual_mode.sh`

这些测试必须保持 repository-local、deterministic、offline，不依赖真实 GitHub、外部网络、或 `git push` 权限。

#### B. Controlled failure-surface tests
需要构造至少一个最小受控场景，证明：
- 默认模式在第一处失败就停止；
- report-all 模式可以继续并累积多个失败；
- 输出末尾存在 failure summary。

关键约束：
- 不要依赖当前仓库真实 failure 的数量和顺序来证明 dual-mode 正确性；
- 应通过可控 fixture / stub checks / 最小受控脚本场景证明 stopping behavior；
- 否则测试会随着仓库真实 failure surface 漂移而变脆。

#### C. Workflow integration verification
需要验证：
- `.github/workflows/preflight.yml` 可切换到 `bash preflight.sh --report-all`；
- 该切换不会削弱 truthful red/green semantics。

推荐通过现有或新增的 workflow contract 测试文件完成，例如扩展：
- `tests/test_github_preflight_workflow.py`

该层仍属于 coder 可完成范围，因为它只验证仓库内 workflow 文件与本地脚本 contract，不要求真实 GitHub run。

#### D. Scope discipline
需要验证：
- 没有引入第二套 preflight entrypoint；
- 没有把 report-all 变成 GitHub-only 魔法模式；
- 没有破坏现有 agent-facing fail-fast 默认行为。

#### E. Capability boundary / non-coder validations
以下验证**不属于 coder 在当前 SDLC 权限模型下必须自动闭环完成的范围**：
- 依赖 `git push` / 创建 PR / 触发真实 GitHub Actions run 的 external witness 验证；
- 任何需要 GitHub UI/API 真实结果来证明 report-all 运行效果的低频外部见证；
- 依赖外部发布权限、外部网络条件、或 operator/manual QA 参与的验收。

这些只应作为 **post-SDLC manual verification** 存在，用于确认：
- GitHub Actions 确实以 `bash preflight.sh --report-all` 运行；
- 真实 GitHub run 能在一次执行中暴露更完整的 failure surface；
- truthful red 语义在真实 GitHub 环境下仍保持成立。

### Quality Goal
本 PRD 的质量目标不是“让 preflight 自动变绿”，也不是“要求 coder 自动证明真实 GitHub witness 已经发生”，而是：

> **在不破坏单一权威 gate 与 truthful failure semantics 的前提下，使 GitHub CI 能一次暴露更完整的 failure surface，同时保持 agent-driven SDLC 继续使用 fail-fast 的小而快闭环。**

边界提醒：
- coder 必须完成 repository-local dual-mode contract、脚本行为、workflow contract 和离线测试；
- coder 不必、也不应在当前 no-push 权限模型下自动完成基于真实 GitHub run 的 witness 验证；
- 如果后续需要确认真实 GitHub report-all 效果，应作为 post-SDLC manual verification / external QA 步骤执行。

## 6. Framework Modifications (框架防篡改声明)
- `/home/openclaw/projects/leio-sdlc/preflight.sh`
- `/home/openclaw/projects/leio-sdlc/.github/workflows/preflight.yml`
- 与 dual-mode preflight contract 直接相关的最小测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: preflight 只有单一 fail-fast 语义，既服务 agent loop 也服务 GitHub CI。
- **Observed limitation**: GitHub CI 虽然 truthful，但每次只能暴露第一个 failure，降低 true-green recovery / backlog formation 效率。
- **v2.0 Revision Rationale**: 保留单一 gate 与 fail-fast 默认值，但增加 report-all 作为显式停止策略，提升 GitHub CI / human audit 的 failure-surface discoverability。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **`default_preflight_command`**:
```text
bash preflight.sh
```

- **`report_all_preflight_command`**:
```text
bash preflight.sh --report-all
```

- **`report_all_mode_name`**:
```text
report-all
```

- **`fail_fast_mode_name`**:
```text
fail-fast
```

- **`single_gate_principle`**:
```text
Fail-fast and report-all must execute the same repository preflight gate. They may differ only in stopping behavior and output aggregation.
```

- **`truthful_failure_requirement`**:
```text
If any preflight check fails, both fail-fast and report-all modes must exit non-zero. Report-all must never convert a failing preflight run into success.
```
