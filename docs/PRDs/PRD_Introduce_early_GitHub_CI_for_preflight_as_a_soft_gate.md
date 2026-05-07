---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Introduce early GitHub CI for preflight as a soft gate

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 当前已经完成 preflight stabilization EPIC (#8) 的 Phase 1：本地 `preflight.sh` 已通过临时 skip / quarantine 恢复为可运行、可交付、可支撑 SDLC 的 gate。

但仅有“本地 temporary green”还不够，因为本地环境会隐藏一类 clean runner 才会暴露的问题，包括：

- 硬编码 `/root/...` 路径假设
- 缺失或不完整的依赖声明
- sandbox / dummy path 假设
- 机器本地状态污染带来的假成功
- CI 与本地执行语义漂移

因此，preflight stabilization 的下一阶段不是立刻追求“true green”，而是先把 `preflight.sh` 接入 GitHub Actions，让 GitHub 的干净 runner 成为一层**可重复、可共享、可观测**的执行面。

本 PRD 的核心目标不是“让 GitHub CI 立刻变绿”，而是：

> **让 `leio-sdlc` 的 GitHub Actions 能真实执行 `bash preflight.sh`，并把成功/失败结果作为一个准确的 soft-gate / observability signal 暴露出来，为后续 failure audit 与 true-green recovery 提供事实基础。**

这一步的设计重点是：

1. 不能把 CI workflow 变成一个“假 preflight”包装器；
2. 不能把对 GitHub 的真实连通性验证，错误地当成每轮 coder-loop 必须依赖的主测试；
3. 必须把“可测试正确性”定义在 workflow contract 正确、执行路径真实、结果传播准确上，而不是定义成“当前仓库所有 preflight 问题已经消失”。

本 PRD 不覆盖：

- preflight 历史失败的 true-green 修复
- hard merge gate / required status check 配置
- GitHub issue sync / PR auto-generation / adapter infra
- 将所有 Phase 3/4 子问题在本 PRD 中一并修复

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须在仓库内新增 GitHub Actions workflow**
   - 在 `leio-sdlc` 仓库内新增一个用于 preflight 的 workflow 文件。
   - 文件路径必须位于 `.github/workflows/` 下。

2. **workflow 必须自动触发**
   - 至少支持：
     - `push`
     - `pull_request`

3. **workflow 必须执行真实的 preflight 入口**
   - CI job 必须调用真实的 `bash preflight.sh`。
   - 不允许以“拆开的近似步骤”替代真实 preflight 作为唯一执行路径。
   - 如需为 runner 做最小 bootstrap，可在 preflight 之前准备 runtime / dependencies，但不能改变 preflight 作为统一 gate 的语义。

4. **workflow 必须在 clean GitHub runner 上运行**
   - 初版使用 GitHub-hosted runner 即可。
   - 其目标是暴露 machine-local success condition 之外的真实问题。

5. **workflow 初期必须作为 soft gate 使用**
   - 本阶段只要求 workflow 结果可见、可重复、可用于 failure audit。
   - 本阶段不要求其成为 merge blocker。
   - 禁止用 `continue-on-error`、吞错误、伪成功状态等方式把真实红灯包装成“软门假绿”。

6. **必须显式定义分层验收策略**
   - 本 PRD 的正确性验证必须分为：
     - 本地可重复的 workflow contract / static validation
     - 本地行为级执行语义验证
     - 真实 GitHub witness 验证（仅作为 SDLC 完成后的低频人工验收指引，不属于本次 SDLC 自动执行闭环）
   - 其中真实 GitHub witness 不得成为每轮 coder-loop 的唯一主验证手段。
   - 本次 SDLC 的完成标准不依赖真实 GitHub witness 已被自动采集或自动落库；该部分仅作为后续人工验收/外部 QA 参考指引存在。

### Non-Functional Requirements

1. **执行语义必须真实**
   - CI 执行的核心 gate 必须与开发者看到的 `preflight.sh` 保持一致。

2. **观测语义必须真实**
   - preflight 成功时，CI job 必须成功。
   - preflight 失败时，CI job 必须失败。
   - 禁止隐藏真实失败。

3. **第一版应最小化 blast radius**
   - 优先新增 workflow 文件与其最小 supporting tests。
   - 不在此 PR 中混入大量 true-green 修复。

4. **必须允许初期 CI 红灯**
   - 红灯是 observability signal，不是 Phase 2 的失败定义。
   - 只要 workflow contract 正确、执行真实、结果传播准确，本阶段就算达成目标。

### User Stories

- **As a leio-sdlc maintainer**, I want GitHub Actions to execute the real `preflight.sh` on clean runners so I can see failures my local machine may hide.
- **As an architect**, I want this phase to define correctness in terms of truthful CI execution and observability, not fake greenness.
- **As a reviewer**, I want the CI integration to be testable without requiring every coder loop to call live GitHub.
- **As a manager**, I want a shared GitHub-visible preflight signal before promoting CI to a hard merge gate.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用**workflow-contract-first + layered acceptance** 的策略。

### 3.1 核心设计原则

1. **GitHub Actions 是 execution surface，不是业务逻辑容器**
   - workflow 负责触发、runner 初始化、调用真实 gate。
   - `preflight.sh` 仍然是仓库级统一 gate 的权威入口。

2. **soft gate ≠ fake green**
   - “soft” 指的是暂时不把 GitHub status 配成 required merge blocker。
   - 不允许通过 `continue-on-error`、额外包装、吞错误等方式制造假成功。

3. **分层验收，避免把 correctness 全压到 live GitHub**
   - 大部分 correctness 必须由本地、可重复、非 flaky 的程序化验证承担。
   - 真实 GitHub run 只作为最终 manual witness，而不是高频主测试。
   - 该 witness 层在本 PRD 中仅提供给 SDLC 完成后的人工验收 / 外部 QA 参考，不属于 planner / coder / reviewer / UAT 的自动闭环交付范围。

4. **先建立观测面，再追 true green**
   - 当前阶段的目标是可靠暴露 clean runner 上的问题。
   - 不是在同一 PR 内消化所有历史 preflight 债务。

### 3.2 目标文件与修改范围

本 PRD 允许修改：

- `leio-sdlc/.github/workflows/preflight.yml`（新增）
- 为 workflow contract / CI semantics 服务的最小测试文件（新增或修改）
- 如确有必要，为 runner bootstrap 提供最小 supporting 文档/脚本（新增或修改）

本 PRD 不授权：

- 以 true-green 为目标的大规模历史测试修复
- 将 GitHub Actions 直接配置为 required status check
- 与 issue sync / PR auto-open / adapter infra 混合实现

### 3.3 Workflow 合同

第一版 workflow 必须满足以下 contract：

1. 文件位于：
   - `.github/workflows/preflight.yml`

2. 触发条件至少包括：
   - `push`
   - `pull_request`

3. workflow 必须包含以下最小步骤，且顺序语义必须清晰可辨：
   - checkout step
   - Python runtime setup step
   - Node runtime setup step
   - minimal bootstrap step
   - `bash preflight.sh` execution step

4. 关于 minimal bootstrap step 的约束：
   - 其目的仅限于让 clean GitHub runner 具备运行当前仓库 `preflight.sh` 的最小前提；
   - 它可以安装当前已知需要的最小依赖集合；
   - 它不得把 preflight 拆解成另一套独立命令链；
   - 它不得把历史 true-green 修复偷偷混入 bootstrap 逻辑；
   - 它不得通过条件跳过、环境短路、假成功包装等方式改变 `preflight.sh` 作为统一 gate 的语义。

5. workflow 不得：
   - 把 preflight 拆成另一套“看起来差不多”的命令并替代真实入口；
   - 用 `continue-on-error` 掩盖 preflight 真实失败；
   - 通过硬编码 success path、空命令、伪造日志或条件跳过把 soft gate 伪装成绿灯；
   - 把“soft gate”实现成“总是成功但附带说明”的假 gate。

6. workflow 成功/失败语义必须保持与 `preflight.sh` 一致：
   - `bash preflight.sh` exit 0 → CI job success；
   - `bash preflight.sh` non-zero exit → CI job failure。

### 3.4 分层验收定义（本 PRD 的关键 correctness contract）

#### Layer A — Local Static / Contract Validation
这层是主验证层，必须稳定、快速、可重复，不依赖 live GitHub。

验证内容包括：

- workflow 文件存在
- workflow YAML 结构满足约定
- `push` / `pull_request` 触发器存在
- preflight job 存在
- 核心执行命令是 `bash preflight.sh`
- workflow 未使用 `continue-on-error` 掩盖真实失败
- workflow 包含 required runtime/bootstrap steps

落地约束：

- 这一层必须通过仓库内本地自动化测试落地；
- 推荐以 Python/pytest 静态 contract tests 读取并断言 `.github/workflows/preflight.yml` 的结构与关键字段；
- 如补充 shell-level assertions，也只能作为附加证据，不得替代结构级 contract tests。

#### Layer B — Local Behavior / Semantics Validation
这层验证 workflow 语义与 preflight 执行传播逻辑，而不依赖真实 GitHub runner。

验证内容包括：

- workflow contract tests 能证明执行目标是仓库真实 gate
- preflight 失败时，job 应视为失败
- preflight 成功时，job 应视为成功
- supporting bootstrap 未改变 preflight 作为统一入口的语义

#### Layer C — External GitHub Witness (Post-SDLC Manual Verification Only)
这层是低频真实见证层，但**不属于本次 SDLC 自动执行闭环**。

验证内容包括：

- workflow pushed to GitHub 后，GitHub Actions 产生真实 run
- 该 run 进入可见终态（success / failure）
- 该结果可在 GitHub UI / API 被观察到

约束：

- 这层是 manual witness，不是每轮 coder-loop 的唯一 gate
- 不得把整个 PRD 的 correctness 仅定义为“live GitHub 必须每次都跑”
- 这层允许较慢、具外部依赖，并且明确依赖外部权限/环境（例如发布到 GitHub 的能力）
- 因此这层**只作为 SDLC 完成后的人工验收 / 外部 QA 指引**，不应被 planner 拆成自动执行 slice，不应成为 coder 的闭环 DoD，也不应成为 UAT 的自动阻断项

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Preflight workflow file exists in the repository**
  - **Given** the Phase 2 implementation branch
  - **When** the repository tree is inspected
  - **Then** a workflow file exists at `.github/workflows/preflight.yml`

- **Scenario 2: Workflow auto-triggers on push and pull request**
  - **Given** the committed preflight workflow
  - **When** the workflow definition is inspected as data
  - **Then** it declares `push` and `pull_request` triggers

- **Scenario 3: Workflow executes the real preflight gate**
  - **Given** the committed preflight workflow
  - **When** the workflow job definition is inspected
  - **Then** the workflow invokes `bash preflight.sh`
  - **And** it does not replace the repository preflight gate with a fake equivalent command chain

- **Scenario 4: Soft gate preserves truthful failure semantics**
  - **Given** the committed preflight workflow
  - **When** the workflow job definition is inspected
  - **Then** it does not use `continue-on-error` or equivalent masking to convert a real preflight failure into a successful CI job

- **Scenario 5: Workflow contract is locally testable without live GitHub dependency**
  - **Given** the workflow file and supporting local tests
  - **When** local automated tests are executed
  - **Then** the workflow contract and execution semantics can be verified without requiring a live GitHub Actions run

- **Scenario 6: External GitHub witness is handled outside SDLC as manual verification**
  - **Given** the repository-local workflow contract and local execution semantics are complete
  - **When** SDLC implementation is handed off for external/manual validation
  - **Then** a maintainer or external QA operator may perform a low-frequency GitHub verification by pushing/opening a qualifying branch or pull request
  - **And** that verification is treated as post-SDLC manual acceptance rather than planner/coder/UAT scope

- **Scenario 7: CI red is acceptable in Phase 2 if it is truthful**
  - **Given** a repository state where `preflight.sh` still exposes historical debt on a clean runner
  - **When** the GitHub workflow is later exercised during manual external witness verification
  - **Then** the workflow may fail
  - **And** that failure is treated as a valid observability signal rather than a Phase 2 design failure

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
本阶段最大的风险不是“CI 一开始会红”，而是：

1. 把 soft gate 做成 fake green；
2. 把 correctness 全压到 live GitHub witness，导致主循环 slow / flaky；
3. workflow 看起来存在，但没有真实执行仓库级 preflight；
4. CI 与本地 preflight 语义漂移，形成第二套 gate。

### Verification Strategy

#### A. Primary Automated Verification (must be local, stable, repeatable)
使用本地自动化测试验证：

- workflow 文件存在与路径正确
- YAML / contract shape 正确
- 触发器存在
- 核心命令为 `bash preflight.sh`
- 未使用 masking 语义掩盖失败
- supporting bootstrap 保持 gate 入口一致性
- required runtime/bootstrap steps 存在

这部分必须作为 coder + preflight + reviewer 主循环的核心证据。

推荐落地方式：

- 新增最小 pytest contract test 文件，对 `.github/workflows/preflight.yml` 做结构级断言；
- 允许补充少量 black-box/supporting tests，但不得把主验证职责转移给 live GitHub API 或人工 UI 检查。

#### B. Secondary Behavioral Verification
验证 workflow 设计语义：

- preflight success/failure 如何映射到 CI job success/failure
- soft gate 定义在“merge policy”而非“伪造成功”上
- workflow 没有偷偷变成另一套独立 gate

#### C. External Witness Verification (Post-SDLC Manual Acceptance Only)
低频执行真实 GitHub witness：

- push / PR 触发真实 workflow run
- GitHub UI 可见 run
- run 结果可观察

这一层只做 manual witness，不做高频主验证，也**不属于本次 SDLC 自动执行闭环**。
它应被视为 SDLC 完成之后，供 maintainer / external QA reference 的手动验收方案。

### Mocking / Dependency Policy
- workflow contract tests 不应依赖 live GitHub API
- 对 GitHub 本体的真实依赖只保留在 manual witness 层
- 如需解析 workflow 文件，应优先做静态/结构级断言，而非 live execution
- planner / coder / reviewer / UAT 不得把 external witness 作为自动闭环交付条件，也不得为此发明额外 slice、procedure 文档或 blocker artifact

### Quality Goal
本 PRD 的质量目标不是“让 `leio-sdlc` preflight 立即 true green”，而是：

> **把 GitHub Actions 建成一个真实执行 `bash preflight.sh`、结果传播准确、对 clean runner 问题可观测、且其大部分正确性可由本地稳定测试验证的 soft-gate CI 表面。**

## 6. Framework Modifications (框架防篡改声明)
- `leio-sdlc/.github/workflows/preflight.yml`（新增）
- 为 workflow contract / CI semantics 服务的最小测试文件（新增或修改）
- 如必要，用于最小 runner bootstrap 的 supporting 文件（新增或修改）

## 6.1 Post-SDLC Manual Verification Instruction (Not in SDLC Scope)
以下内容**不是本次 SDLC 自动执行闭环的一部分**，仅作为 SDLC 完成后供 maintainer / external QA 参考的手动验收方案：

1. 将包含 `.github/workflows/preflight.yml` 的实现分支 push 到 GitHub，或创建/更新相应 pull request。
2. 在 GitHub Actions UI 或使用一次性 `gh` / GitHub API 查询，确认 `Preflight` workflow 产生真实 run。
3. 观察该 run 的终态（`success` / `failure` / 其他 GitHub 可见终态）。
4. 若需要留存外部验收记录，可在人工验收阶段单独记录：
   - workflow name: `Preflight`
   - workflow path: `.github/workflows/preflight.yml`
   - trigger event: `push` or `pull_request`
   - head SHA
   - run URL or database id
   - terminal conclusion
   - capture timestamp/date
5. 该人工验收层若发现问题，应作为后续 issue / hotfix 输入，而不是要求本次 planner / coder / reviewer / UAT 自动闭环处理。

明确约束：
- planner 不得为该人工验收层自动生成 slice；
- coder 不得把该层当作当前 PR 的自动 DoD；
- reviewer 不得因缺少真实 GitHub witness 而要求在无外部发布权限的 coder loop 中伪造 placeholder；
- UAT 不得把该层作为本次 SDLC 自动阻断项。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 直接把“GitHub 上真实跑起来”当成 Phase 2 的 correctness，隐含把 live GitHub run 作为主验证环。
- **Audit Concern**: 这种定义会把 Phase 2 变成高外部依赖、慢、潜在 flaky 的工作，削弱 SDLC 主循环的程序可验证性。
- **v2.0 Revision Rationale**: 改为分层验收定义：把绝大部分 correctness 收敛到本地稳定的 workflow contract / semantics tests，再保留一个低频 GitHub witness 作为真实接线见证。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`workflow_relative_path`**:
```text
.github/workflows/preflight.yml
```

- **`workflow_gate_command`**:
```text
bash preflight.sh
```

- **`workflow_required_triggers`**:
```text
push
pull_request
```

- **`workflow_required_minimal_steps`**:
```text
checkout
python-runtime-setup
node-runtime-setup
minimal-bootstrap
bash preflight.sh
```

- **`workflow_success_failure_mapping`**:
```text
bash preflight.sh exit 0 -> CI job success
bash preflight.sh non-zero exit -> CI job failure
```

- **`soft_gate_semantics_statement`**:
```text
Phase 2 soft gate means the GitHub Actions result is visible and truthful, but not yet configured as a required merge blocker.
```

- **`masking_prohibition_statement`**:
```text
Do not use continue-on-error or any equivalent masking mechanism to convert a real preflight failure into a successful CI result.
```

- **`local_contract_test_expectation`**:
```text
The primary correctness checks for this phase must be implemented as repository-local automated contract tests against .github/workflows/preflight.yml rather than as live GitHub-only verification.
```
