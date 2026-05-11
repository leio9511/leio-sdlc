---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Runtime Path Resolution and Auditor Artifact Placement Cleanup

## 1. Context & Problem (业务背景与核心痛点)
当前 `leio-sdlc` 在 control-plane 运行产物落点上存在两类高度相关、且会互相放大影响的缺陷：

1. **`GLOBAL_RUN_DIR` 的 `~` 解析错误**（issue #38）
   - 当配置写成 `~/.sdlc` 时，`orchestrator.py` 目前直接对原字符串做 `os.path.abspath(...)`，没有先做 `os.path.expanduser(...)`；
   - 结果 `~` 被当作字面相对路径片段，而不是用户 home；
   - 运行产物会错误落到 repo 内部，例如：
```text
/home/openclaw/projects/leio-sdlc/~/.sdlc/.sdlc_runs/...
```
   而不是预期的：
```text
/home/openclaw/.sdlc/.sdlc_runs/...
```

2. **Auditor 运行后向目标 repo 留下 framework-owned 调试产物**（issue #19）
   - `spawn_auditor.py` 当前会把 `auditor_debug/`、startup packet、rendered prompt、canonical verdict 等运行产物保存到 `run_dir`；
   - 但在真实 PM → Auditor → SDLC flow 中，如果 `run_dir` 没有被明确锚定到 framework-owned global run directory，而是退化成目标 repo workdir 或其子路径，就会让这些 framework-owned 产物变成 repo 内的 untracked files；
   - 随后的 `orchestrator.py` 启动会执行 dirty workspace guardrail，并把这些 framework 自己留下的产物当成用户工作区污染，从而中断 SDLC 启动。

这两个问题本质上不是彼此独立的随机 bug，而是共享一个更高层的 contract 失真：

> **framework-owned runtime/debug artifacts 必须默认落在 framework-owned run area，而不是业务 repo workspace。**

如果只修 #38，不收紧 auditor artifact placement contract，那么 auditor 仍然可能继续把 repo 弄脏；
如果只修 #19，但 `GLOBAL_RUN_DIR` 仍然错误解析到 repo 内部，那么 control-plane 产物依旧会在错误位置积累。

本 PRD 的目标是把这两类问题合并成一次窄边界、contract-first 的修复：
- 统一修正 `GLOBAL_RUN_DIR` / `--global-dir` 的 home-relative 路径解析语义；
- 明确 Auditor 的 debug / verdict / envelope artifacts 必须跟随 canonical run dir，而不是随意落在 repo 根；
- 让正常 PM → Auditor → SDLC happy path 不再因为 framework 自己留下的产物触发 dirty workspace 失败。

本 PRD **不**处理：
- worktree architecture / parallel workspace isolation（issue #33）；
- branch lifecycle / PR lifecycle / GitHub integration；
- generalized control-plane/data-plane platform rewrite；
- generalized reviewer / verifier / planner artifact-progress contract；
- 用“简单把 framework 产物加入 dirty-workspace ignore 白名单”来掩盖落点 contract 错误。

## 2. Requirements & User Stories (需求定义)
### Functional Requirements

1. **必须冻结 global runtime path resolution contract**
   - 对 runtime/global directory 相关输入，必须统一遵循：
     1. 先做 `os.path.expanduser(...)`
     2. 再做 `os.path.abspath(...)`
   - 至少包括：
     - `orchestrator.py` 中来自 `--global-dir` 的输入
     - `orchestrator.py` 中来自 `app_config["GLOBAL_RUN_DIR"]` 的输入
   - 不允许继续保留“CLI 路径正确、config 路径错误”或反之的双重语义。

2. **必须冻结 framework-owned run area contract**
   - 当 global run directory 被显式指定（CLI 或 config）时，framework-owned runtime artifacts 必须落在该 canonical run area 中；
   - 不允许因为 `~` 没有被展开、或因为 fallback 逻辑混乱，而把 `.sdlc_runs` / `auditor_debug` / verdict 文件错误落到业务 repo 内部。

3. **必须冻结 Auditor artifact placement contract**
   - `spawn_auditor.py` 的以下产物必须保存到 framework-owned run dir / run-specific directory，而不是 target repo root：
     - `auditor_debug/`
     - `auditor_verdict.json`
     - startup packet / rendered prompt 等 envelope artifacts
   - 测试环境仍可通过 `SDLC_RUN_DIR` 显式注入临时目录；
   - 但真实 flow 下的默认/推荐路径语义必须与 canonical global run area 对齐。

4. **必须冻结 happy-path non-pollution contract**
   - 从 clean git workspace 开始，完成一次成功 auditor run 后，framework-owned artifacts 不得以 untracked repo dirt 的形式残留在 target repo root；
   - 随后的 orchestrator startup 不得仅仅因为 auditor 自己留下的产物而触发：
```text
[FATAL] Dirty Git Workspace detected!
```

5. **不得通过放宽 dirty-workspace guardrail 掩盖错误落点**
   - 本 PRD 的主修复方向必须是“把 framework 产物写到正确位置”；
   - 不允许仅通过把 `auditor_debug/` 等名字加入 dirty-workspace 特判 ignore 白名单来制造表面成功；
   - 如需少量兼容性 guardrail，仅能作为补强，不能替代正确的 artifact placement contract。

6. **历史错误落点的残留处理必须是安全、有限、显式的**
   - 如果实现选择清理 repo 内错误生成的 `~/` 路径或 auditor 临时产物，必须限定在 framework-owned、可明确识别的路径；
   - 不允许引入模糊、破坏性、可能误删用户文件的 repo cleanup 逻辑。

### Non-Functional Requirements

1. **本 PRD 必须保持窄边界**
   - 只允许修复 19/38 对应的 runtime path resolution 与 auditor artifact placement contract；
   - 不得扩张为整个 control-plane/data-plane 分离工程重构。

2. **实现命名语义必须更清楚**
   - 推荐在新增 helper 或局部重构时显式区分：
     - raw configured path
     - resolved global dir
     - workdir
     - run dir
   - 不允许继续让“repo 工作目录”和“framework run 目录”在语义上混用。

3. **测试必须证明黑盒行为，而不是只证明内部 helper 被调用**
   - 至少要验证真实路径结果、repo 是否仍然 clean、以及 auditor 产物的实际落点；
   - 不允许只加 mock-heavy 内部函数断言却不覆盖最终可观察行为。

### User Stories

- **As an operator**, I want `GLOBAL_RUN_DIR="~/.sdlc"` to resolve to my actual home directory, so framework runtime state never silently lands under the project repo.
- **As a maintainer**, I want auditor debug/verdict artifacts to live in a framework-owned run area instead of the target repo root, so a successful audit does not poison the next orchestrator startup.
- **As a reviewer**, I want this fix scoped specifically to runtime path resolution and auditor artifact placement, so the execution brief remains small, auditable, and unlikely to drift into a larger architecture rewrite.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
本 PRD 采用 **contract-first runtime artifact placement cleanup** 路线：

- 先写死 path resolution contract；
- 再写死 auditor artifact placement contract；
- 再让 tests 围绕“实际落点 / repo 不再被弄脏 / 后续 orchestrator 不再被 framework 垃圾拦住”来收敛；
- 不用 ignore 白名单伪修复，也不做平台级重构。

### 3.1 冻结的 authoritative contract

#### A. Global-dir resolution
对任意 runtime/global dir 输入值 `raw_path`：
```text
resolved_path = abspath(expanduser(raw_path))
```

适用面：
- `--global-dir`
- `GLOBAL_RUN_DIR` config

#### B. Canonical framework-owned run area
当 global run dir 被指定后：
```text
GLOBAL_DIR = <resolved_global_dir>
RUNS_ROOT = <GLOBAL_DIR>/.sdlc_runs
```

任意 run-specific artifacts（含 auditor 相关 envelope/debug/verdict）都必须以该 run area 为根，而不是 target repo root。

#### C. Auditor artifact placement
对一次 auditor run，其 framework-owned 产物（含 `auditor_debug/`、`auditor_verdict.json`、startup packet、rendered prompt）必须落在：
```text
<run_specific_dir>/...
```
其中 `<run_specific_dir>` 是 canonical run area 中的本次 run 目录。

#### D. Repo cleanliness rule
Auditor 成功后，如果 target repo 在启动前是 clean，那么：
- auditor 不得让 target repo root 新增 framework-owned untracked artifacts；
- orchestrator 后续 dirty-workspace check 不得因为 framework 自己的残留而失败。

### 3.2 具体改动方向

#### A. `scripts/orchestrator.py`
必须对齐新的 global-dir resolution contract：
- `args.global_dir` 先 `expanduser` 再 `abspath`
- `app_config["GLOBAL_RUN_DIR"]` 先 `expanduser` 再 `abspath`
- 如有局部 helper，可抽一个统一 resolver，避免 CLI/config 两套漂移语义

同时要检查 orchestrator 在初始化 run dir / job dir 时，不再把 control-plane 产物锚到 repo 内的错误 `~/...` 路径。

#### B. `scripts/spawn_auditor.py`
必须对齐 canonical run-dir contract：
- Auditor 的 output / debug / envelope artifacts 必须明确写入 run-specific framework-owned area；
- 不能因为默认 `run_dir='.'` 或未注入 `SDLC_RUN_DIR` 而把 `auditor_debug/` 落到 target repo root；
- 允许测试通过 `SDLC_RUN_DIR=<tmpdir>` 明确注入临时目录，但真实路径语义必须清晰且可预测。

必要时可以：
- 增加一个小型 resolver，用于统一 Auditor 的 run dir 来源与绝对路径归一化；
- 但不允许引入与 orchestrator 完全割裂的第二套 run-area 语义。

#### C. Tests
建议覆盖两类黑盒面：

1. **Path resolution black-box tests**
   - 验证 `GLOBAL_RUN_DIR="~/.sdlc"` 会落到真正的 home，而不是 repo 下的 `~/...`
   - 如有 CLI `--global-dir` 路径测试，也要对齐同一 contract

2. **Auditor non-pollution / artifact placement tests**
   - clean repo + temporary global run dir / run dir
   - auditor 成功后：
     - framework-owned artifacts 出现在 run dir 中
     - target repo 不出现 `auditor_debug/` untracked dirt
   - 必要时补一条 orchestrator startup / dirty-workspace 相关回归，证明不会因 auditor 残留而被拦住

### 3.3 明确不采用的方案

1. **不只在 dirty-workspace guard 增加 ignore 名单**
   - 这只是掩盖错误落点，不是修 contract。

2. **不扩张成 control-plane/data-plane 全面重构**
   - 不在本 PRD 内引入 worktree、branch lifecycle、全局 metadata registry 等平台级设计。

3. **不使用破坏性 repo cleanup 作为主修复路径**
   - 不能靠广义 `rm -rf` 或模糊路径匹配去“清干净再说”。

4. **不把 auditor artifact 随便挪到 repo 内另一个隐藏目录就算完**
   - 如果它仍然属于 target repo workspace，就仍然会污染 git 视图或制造 guardrail 例外；
   - 正确方向是 framework-owned run area，而不是 repo 内换个角落继续堆控制面垃圾。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: `GLOBAL_RUN_DIR` with `~` resolves to the user home rather than a repo-local literal `~` path**
  - **Given** `GLOBAL_RUN_DIR` is configured as `~/.sdlc`
  - **When** orchestrator resolves the global run directory
  - **Then** the resolved path is under the executing user home
  - **And** it is not anchored under `<repo_root>/~/...`

- **Scenario 2: auditor artifacts are written into the framework-owned run area instead of the target repo root**
  - **Given** a clean target git workspace and a canonical global run directory
  - **When** `spawn_auditor.py` runs successfully for a valid PRD
  - **Then** `auditor_debug/`, `auditor_verdict.json`, and envelope artifacts are created under the run-specific framework-owned directory
  - **And** those artifacts are not created at the target repo root

- **Scenario 3: a successful auditor run does not poison the subsequent orchestrator startup with framework-owned repo dirt**
  - **Given** a clean target git workspace
  - **And** a successful auditor run has just completed
  - **When** orchestrator performs its startup dirty-workspace validation
  - **Then** the workspace is not rejected solely because of framework-owned auditor artifacts

- **Scenario 4: explicit CLI/config path sources follow one unified resolution contract**
  - **Given** a home-relative runtime path is provided via config or CLI
  - **When** the runtime directory is resolved
  - **Then** both sources follow the same `expanduser` → `abspath` contract
  - **And** they do not diverge into different final locations

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险不是单一函数逻辑错，而是 **control-plane artifact placement contract 继续漂移**：
- 一边修了 `GLOBAL_RUN_DIR`，另一边 auditor 还在往 repo 根写；
- 或测试只证明 helper 被调用，却没有证明 repo 不再被弄脏；
- 或实现通过 dirty-workspace ignore 伪修复而掩盖错误落点。

### 推荐测试策略

1. **以黑盒路径结果为主**
   - 优先验证实际文件落点、绝对路径、repo cleanliness；
   - 不把测试重心放在内部 helper 名称或实现细节上。

2. **适度 mock，避免过度 mock**
   - 可以 mock LLM 调用 / ignition handshake 等外部依赖，保证 auditor tests 稳定；
   - 但 run dir / artifact saving / path resolution / repo cleanliness 应尽量真实落盘验证。

3. **需要至少一组临时目录隔离测试**
   - 使用 `tmp_path` / 临时 home / 临时 run dir 来验证 `~` 展开与 auditor artifact placement；
   - 避免依赖主仓库或主机已有污染状态。

4. **需要回归 dirty-workspace 相关行为**
   - 至少证明 framework-owned auditor artifacts 不再成为正常 happy path 的阻断项；
   - 但不要把测试扩张成整套 orchestrator E2E 大场景。

### Quality Goal
修复完成后，`leio-sdlc` 必须满足以下质量目标：
- control-plane 运行产物默认不再污染业务 repo workspace；
- `GLOBAL_RUN_DIR="~/.sdlc"` 行为对人类操作员是直觉正确的；
- auditor 成功 → orchestrator 启动 的 happy path 不再因 framework 自己的产物而被打断。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/spawn_auditor.py`
- 与上述 contract 直接相关的最小测试文件（例如现有 `tests/test_auditor.py`、`tests/test_spawn_auditor.py`，以及必要的新回归测试）

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 将 issue #19（auditor leaves untracked workspace artifacts）与 issue #38（GLOBAL_RUN_DIR expanduser bug）合并为一次窄边界的 runtime artifact placement cleanup。
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
None
