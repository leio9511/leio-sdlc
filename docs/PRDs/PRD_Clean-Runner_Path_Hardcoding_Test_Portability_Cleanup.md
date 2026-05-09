---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Clean-Runner Path Hardcoding Test Portability Cleanup

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 的 GitHub-hosted `Preflight` 在 clean runner 上仍然存在 pytest failure surface。当前已经确认的一类明确问题不是产品逻辑回归，而是**测试本身把宿主机绝对路径硬编码成前提条件**，导致测试只能在特定开发机路径布局下通过，无法在 GitHub clean runner 或其他仓库根目录位置稳定运行。

这类问题目前在代码/测试层面的已知命中包括：

1. `tests/test_orchestrator_session_strategy.py`
   - 通过 autouse fixture 强行 `os.chdir("/root/projects/leio-sdlc")`
   - 在 clean runner 上触发 `PermissionError` / path portability failure

2. `tests/test_planner_envelope_forward_compatibility.py`
   - 直接硬编码 `"/root/projects/leio-sdlc/playbooks/planner_playbook.md"`
   - 将测试与特定宿主路径绑定，而不是与仓库相对结构绑定

3. `tests/test_pr_005_audit_verification.sh`
   - 直接使用 `"/root/projects/leio-sdlc/..."` 指向仓库内文件
   - 使 shell 测试依赖固定绝对路径，而不是当前 checkout 的实际 repo root

这类问题的共同特征：
- 它们属于 **test portability debt**，不是产品功能缺陷；
- 它们会污染 clean-runner 信号，使 CI 无法区分“产品坏了”还是“测试写死了宿主路径”；
- 它们适合一次性、窄范围、同类治理地修复，因为根因一致，修改边界清晰。

本 PRD 的目标不是把整个 pytest suite 变绿，也不是处理其它 mock/assert drift、handoff debt、或 branch/witness 问题，而是：

> **一次性清理当前测试代码中的仓库根目录硬编码路径依赖，让这些测试在任意 clean checkout 路径下都通过相对定位找到 repo 内资源。**

本 PRD 不覆盖：
- PRD / docs 内出现的历史绝对路径字符串；
- `.tmp` / log / generated artifacts 中的历史路径内容；
- 与宿主路径无关的 pytest assertion drift；
- branch promotion、manual witness、GitHub-hosted proof 的流程问题；
- 为了“顺手变绿”而扩大到其它无关测试清理。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须移除测试代码中对 `/root/projects/leio-sdlc` 的运行时依赖**
   - `tests/test_orchestrator_session_strategy.py` 不得再要求当前工作目录必须切到 `/root/projects/leio-sdlc`；
   - `tests/test_planner_envelope_forward_compatibility.py` 不得再通过硬编码绝对路径定位 `playbooks/planner_playbook.md`；
   - `tests/test_pr_005_audit_verification.sh` 不得再通过硬编码绝对路径定位仓库内 audit / rollback 相关文件。

2. **测试必须改为通过仓库相对结构或动态 repo-root 推导定位资源**
   - Python 测试应优先基于 `__file__` / `Path(...).resolve()` / `os.path.dirname(__file__)` 推导 repo root；
   - Shell 测试应优先基于脚本自身位置计算 `SCRIPT_DIR` 与 `REPO_ROOT`；
   - 不得用另一个新的宿主绝对路径替换旧的宿主绝对路径。

3. **修复后必须保持测试原始业务意义**
   - `test_orchestrator_session_strategy.py` 仍然要验证 orchestrator 对 `coder-session-strategy` 的行为；
   - `test_planner_envelope_forward_compatibility.py` 仍然要验证 planner envelope / playbook 路径相关 contract；
   - `test_pr_005_audit_verification.sh` 仍然要验证 audit artifact / rollback contract，而不是被简化为只检查文件存在。

4. **不得通过跳过测试、弱化断言、或恢复 ignore 来解决 clean-runner path 问题**
   - 不允许通过把这些测试重新加入 ignore list 来回避修复；
   - 不允许改成 `if path exists then pass` 之类空壳测试；
   - 修复必须来自路径解析方式正确，而不是降低测试价值。

### Non-Functional Requirements

1. **blast radius 必须受控**
   - 优先只修改已识别的测试文件；
   - 除非某个共享 helper 是明显更小的收敛点，否则不要顺带重构产品代码。

2. **clean-runner portability 必须成为显式设计目标**
   - 测试应当能在 GitHub Actions checkout、任意本地 clone 路径、以及 sandbox 环境下运行；
   - 测试不应假设 repo 位于 `/root/projects/...`、`/home/...` 或任何固定宿主布局。

3. **同类问题应一次性治理**
   - 对当前已确认的同类硬编码路径测试点，允许在同一轮修复中一起清理；
   - 但只限“仓库根路径硬编码 portability debt”，不得借机扩张到其它 pytest debt。

### User Stories

- **As a CI maintainer**, I want tests to locate repository files relative to the actual checkout root, so GitHub-hosted runners do not fail on nonexistent developer-machine paths.
- **As a reviewer**, I want portability fixes to preserve the original assertions, so the suite still verifies behavior instead of turning into a file-existence shell.
- **As an engineer running local clones in arbitrary directories**, I want these tests to pass regardless of where the repository is checked out, so path assumptions do not create false negatives.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本方案采用 **repo-root dynamic resolution** 路线：
- 将测试对仓库资源的定位从“宿主机固定绝对路径”改为“基于测试文件位置动态推导 repo root”；
- 在 Python 测试中统一使用 `Path(__file__).resolve()` 或等价 `os.path` 推导；
- 在 shell 测试中统一使用脚本目录反推 `REPO_ROOT`。

### 3.1 核心设计决策

1. **把 `/root/projects/leio-sdlc` 视为环境偶然性，而不是 contract**
   - 它可能反映历史开发机布局，但不是测试 contract 的组成部分；
   - 测试 contract 应该绑定仓库结构，而不是绑定宿主路径。

2. **优先在测试层修复，不把 portability debt 转嫁给产品代码**
   - 当前问题是测试假设错位；
   - 如果仅通过修改测试路径解析就能恢复 portability，不应借机改 orchestrator / planner / audit 运行时代码。

3. **保留行为断言，替换路径获取方式**
   - 目标是“同样的测试意图，在正确的路径解析下继续成立”；
   - 不是“删掉断言让 CI 绿”。

4. **一次性处理当前已确认的同类点，但不扩大问题类型**
   - 当前已确认的 3 个测试文件属于同一类 root-cause；
   - 可以同一轮修掉；
   - 但不顺手处理 mock argv drift、handoff debt、或其它 unrelated pytest failures。

### 3.2 推荐实现方向

#### A. `tests/test_orchestrator_session_strategy.py`
- 用 repo-root 动态解析替代 `os.chdir("/root/projects/leio-sdlc")`；
- 更稳的方式是保存并恢复 cwd，避免 fixture 对全局工作目录造成不可移植副作用；
- 仍保留通过 subprocess / patched orchestrator.main 验证 session strategy 的现有测试意图。

#### B. `tests/test_planner_envelope_forward_compatibility.py`
- 将 `playbook_path` 改为从当前测试文件相对定位到 `playbooks/planner_playbook.md`；
- 不要把 playbook 路径写死到开发机绝对地址。

#### C. `tests/test_pr_005_audit_verification.sh`
- 用脚本目录推导 `REPO_ROOT`；
- 通过 `"$REPO_ROOT/..."` 定位 audit file / rollback script；
- 保持 shell 验证逻辑不变，仅替换路径来源。

### 3.3 明确不采用的方案

1. **不通过重新 ignore 这些测试来实现 green**
   - 这只是隐藏 portability debt。

2. **不通过把硬编码路径改成另一个绝对路径来“适配 CI”**
   - 例如 `/home/runner/work/...` 也同样是错误方向。

3. **不把这轮修复扩大成全量 pytest cleanup**
   - 当前 brief 只处理 root-path hardcoding portability 问题。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: Orchestrator session strategy tests no longer depend on a fixed host path**
  - **Given** the repository is checked out in an arbitrary filesystem location
  - **When** `tests/test_orchestrator_session_strategy.py` is executed
  - **Then** the test does not attempt to `chdir` into `/root/projects/leio-sdlc`
  - **And** the session-strategy assertions still execute against the intended orchestrator behaviors

- **Scenario 2: Planner envelope forward-compatibility test resolves the playbook from the actual repo root**
  - **Given** the repository is checked out in an arbitrary filesystem location
  - **When** `tests/test_planner_envelope_forward_compatibility.py` is executed
  - **Then** it resolves `playbooks/planner_playbook.md` relative to the real repository layout
  - **And** it does not require a developer-machine absolute path

- **Scenario 3: Audit verification shell test resolves repo files relative to script location**
  - **Given** the repository is checked out in an arbitrary filesystem location
  - **When** `tests/test_pr_005_audit_verification.sh` is executed
  - **Then** it locates audit/rollback artifacts through a computed `REPO_ROOT`
  - **And** it does not depend on `/root/projects/leio-sdlc`

- **Scenario 4: Portability fixes preserve test intent**
  - **Given** the three targeted tests have been updated for dynamic repo-root resolution
  - **When** they are run in a clean environment
  - **Then** failures, if any, come from their real business assertions rather than host-path lookup errors
  - **And** no test has been reduced to a no-op or file-existence-only check

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
### Core Quality Risk
当前最大的风险不是“路径写死不好看”，而是：

1. clean-runner 上的 pytest 结果被宿主路径假设污染，导致 failure surface 失真；
2. 修复过程中为了快速变绿而弱化测试意图；
3. 一次性扫同类问题时顺手扩大到其它 unrelated pytest debt，重新引入边界失控。

### Verification Strategy

#### A. Focused test execution
需要优先验证：
- `tests/test_orchestrator_session_strategy.py`
- `tests/test_planner_envelope_forward_compatibility.py`
- `tests/test_pr_005_audit_verification.sh`

这些应在当前仓库真实路径下通过 repo-root dynamic resolution 运行，而不是依赖固定 host path。

#### B. Regression containment
需要确认：
- 修改仅限当前识别的同类 portability 点；
- 不引入产品代码行为变化；
- 不通过 skip / ignore / hollow assertions 制造假绿。

#### C. Clean-runner signal quality
在本地 focused 验证通过后，可以将 GitHub-hosted `Preflight` 作为**后验确认信号**：与这三处相关的路径错误应消失；如果 suite 仍失败，失败应来自剩余真实 pytest debt，而不是 `/root/projects/leio-sdlc` 这类宿主路径假设。

注意：GitHub-hosted `Preflight` 在本 PRD 中**不是完成条件本身**，也不是 manual witness gate。当前 brief 的完成仍以 repository-local evidence 为准。

### Quality Goal
本 PRD 的质量目标不是“一次让整个 pytest suite 变绿”，而是：

> **一次性消除当前测试代码中已确认的仓库根路径硬编码，让 clean-runner pytest/preflight 信号不再被宿主绝对路径假设污染。**

补充边界：本 PRD 的完成以 repository-local focused verification 为准；GitHub-hosted `Preflight` 仅用于后验确认 clean-runner 信号是否被净化，不构成额外的 branch/witness/completion gate。

## 6. Framework Modifications (框架防篡改声明)
- `tests/test_orchestrator_session_strategy.py`
- `tests/test_planner_envelope_forward_compatibility.py`
- `tests/test_pr_005_audit_verification.sh`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 从 #26 当前 clean-runner failure surface 中识别出首个明确 portability 子类问题：测试代码把 `/root/projects/leio-sdlc` 当作运行时前提。
- **v1.1 Scope Clarification**: 明确只处理代码与测试层的 root-path hardcoding，不处理 PRD/docs/history artifacts。
- **v1.2 Consolidation Rationale**: 已确认 3 个测试文件属于同类 root-cause，决定一次性同类治理，而不是逐个文件零散修补。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:
- **None**

