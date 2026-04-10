---
Affected_Projects: [List the target projects here, e.g., leio-sdlc, AMS]
---

# PRD: HOTFIX_SDLC_TDD_and_Config_Parser_Recovery

## 1. Context & Problem (业务背景与核心痛点)
当前 SDLC 管道陷入瘫痪（无法 Deploy 且持续报错）。原因主要有两点：
1. **测试策略与 PR 拆分违规 (TDD 破裂)**：之前的 Planner 错误地将测试（尤其是被错当成 E2E 的轻量级验证）与代码实现分拆在不同的 PR 中，导致单独合并实现时 CI 挂掉。正确的做法是，所有的验证都应挂载为轻量级单元测试（命名为 `test-` 而非 `e2e-`），放入 `preflight.sh`，并且在一个 PR 内完成。
2. **Config 生成误判代码区**：这本是 ISSUE-1094 中的问题，但在自动化测试环境（如 `SDLC_TEST_MODE=true`）中，`orchestrator.py` 会在当前代码区生成物理的 `sdlc_config.json` 文件，污染了 Git Status，导致严苛的脏状态守卫被触发，使流水线强制熔断。

为快速恢复 SDLC 正常工作，Boss 指示挂起庞杂的 1094，提炼出这几个阻断性 Bug 形成单独的 Hotfix PRD，用一个自包含的 PR 一次性修复。

## 2. Requirements & User Stories (需求定义)
1. **测试降维挂载**：将原本针对 1094 (部署路径和配置隔离) 计划的 e2e 测试改写为轻量级的 `scripts/test_1094_deploy_and_config.sh`（或拆分为 `test_deploy_paths.sh` 和 `test_config_pollution.sh`），使其能被 `preflight.sh` 自动抓取和秒级执行。
2. **Hermetic Config Loading 修复**：在 `scripts/orchestrator.py` 的 `load_or_merge_config` 中，如果检测到 `os.environ.get("SDLC_TEST_MODE") == "true"`，则**绝对禁止**将生成的默认配置写入磁盘，只返回内存合并后的 Dict。
3. **部署脚本路径修复**：给 `kit-deploy.sh`、`deploy.sh` 以及 `TEMPLATES/scaffold/profiles/skill/deploy.sh` 首部加入 `cd "$(dirname "$0")" || exit 1` 防止依赖运行路径而提取到错误的 slug。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
> **[Instruction to Main Agent/Architect]**
本 Hotfix 采取**“单 PR 大包围”**的 TDD 策略，避免拆分导致的 CI 标红。
1. **修复 `orchestrator.py`**：找到 `load_or_merge_config`，在写盘操作前包裹 `if os.environ.get("SDLC_TEST_MODE") != "true":`。
2. **修复 Deploy Scripts**：在三个部署脚本顶部追加路径安全语句。
3. **建立轻量级 Bash 测试 (`scripts/test_1094_hotfix.sh`)**：
   - 验证执行 `deploy.sh` 时，路径提取不发生飘移。
   - 验证在 `SDLC_TEST_MODE=true` 时，执行 `orchestrator.py` 后不会物理生成 `config/sdlc_config.json` 文件。
必须确保这些变动作为一个统一的 PR 提交，保证 `preflight.sh` 一遍绿。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 测试配置生成不污染环境**
  - **Given** 当前环境下 `SDLC_TEST_MODE=true`，且 `config/` 目录为空
  - **When** 尝试启动 `orchestrator.py` 并触发配置加载逻辑
  - **Then** 工作区不会凭空生成物理文件 `config/sdlc_config.json`
- **Scenario 2: 测试轻量级挂载与 CI 绿灯**
  - **Given** 新增了轻量级测试 `scripts/test_1094_hotfix.sh`
  - **When** 运行 `preflight.sh`
  - **Then** 该测试被成功执行、通过，且最终打印测试全绿（0 失败）。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **拒绝重度 E2E 测试**：不要去写那些耗时长的 `scripts/e2e/e2e_*.sh`。一切回归到本工程的快速测试理念，使用简单的 `test_*.sh` 来做快速集成。
- **Git 污染断言**：测试脚本执行完配置生成调用后，必须使用 `[ -f "config/sdlc_config.json" ]` 进行断言检查。如果存在，退出码为 1。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `kit-deploy.sh`
- `deploy.sh`
- `TEMPLATES/scaffold/profiles/skill/deploy.sh`
- 新增 `scripts/test_1094_hotfix.sh`

## 7. Hardcoded Content (硬编码内容)
None.
