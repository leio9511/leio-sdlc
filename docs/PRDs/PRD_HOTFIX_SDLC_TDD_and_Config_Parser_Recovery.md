---
Affected_Projects: [leio-sdlc]
---

# PRD: HOTFIX_SDLC_TDD_and_Config_Parser_Recovery

## 1. Context & Problem (业务背景与核心痛点)
当前 SDLC 流水线存在两个阻断性的基础问题，导致流水线瘫痪，需要紧急 Hotfix：
1. **测试脚本分类与路径混乱**：存在轻量级的验证测试被错误地归类为 `e2e` 类测试。因为其本身较轻量，应该直接作为常规的 Bash 测试被 `preflight.sh` 自动挂载，而不是走繁重的 e2e 流程。
2. **测试环境误判导致代码区污染**：在自动化测试环境（如 `SDLC_TEST_MODE=true`）下，`orchestrator.py` 在加载配置时会错误地在当前代码工作区生成物理文件 `config/sdlc_config.json`。这个本不该生成的物理文件会导致 Git 工作区状态变脏，从而错误地触发流水线的严格脏状态熔断保护。

## 2. Requirements & User Stories (需求定义)
1. **纠正测试脚本路径与命名**：新增轻量级 Bash 测试脚本 `scripts/test_1094_config_pollution.sh`。这替代了原先规划的重度 e2e 验证逻辑，确保被 `preflight.sh` 直接识别为快速单元测试。
2. **修复配置加载机制**：在 `scripts/orchestrator.py` 的配置加载机制中，如果检测到处于测试模式（`os.environ.get("SDLC_TEST_MODE") == "true"`），系统只能在内存中合并和返回配置数据，**绝对禁止**向磁盘写入任何物理配置文件。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
> **[Instruction to Main Agent/Architect]**
本 Hotfix 必须在一个自包含的 PR 内完成所有实现与验证：
1. **测试降维挂载**：创建 `scripts/test_1094_config_pollution.sh`。脚本需 `export SDLC_TEST_MODE=true`，触发一次 `orchestrator.py`（例如调用 `--help` 或直接 import 测试），随后使用 `[ ! -f "config/sdlc_config.json" ]` 断言物理文件没有被错误生成，并在成功后打印指定字符串。
2. **拦截写盘操作**：定位 `scripts/orchestrator.py` 中的 `load_or_merge_config` 函数。在执行 `os.makedirs` 和 `open(..., "w")` 等操作前，包裹条件守卫 `if os.environ.get("SDLC_TEST_MODE") != "true":`。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 测试配置生成不污染环境**
  - **Given** 当前环境下设置了 `SDLC_TEST_MODE=true`
  - **When** 触发 `orchestrator.py` 的配置加载逻辑
  - **Then** 工作区内不会物理创建出 `config/sdlc_config.json` 文件。
- **Scenario 2: 测试脚本正确挂载与输出**
  - **Given** 新增了验证用的测试脚本 `scripts/test_1094_config_pollution.sh`
  - **When** 运行该测试脚本
  - **Then** 脚本在成功断言无文件生成后，控制台需精准输出 `[PASS] test_1094_config_pollution passed successfully`。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
本 PRD 核心是恢复流水线健康。主要的验证手段即是通过被降维挂载至 `preflight.sh` 中的 `test_*.sh` 脚本来进行防回归测试。只要配置不再被错误地写盘，Git Status 就能保持干净，流水线的脏状态熔断便不会被错误触发。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- 新增 `scripts/test_1094_config_pollution.sh`

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **`test_config_pollution_success_message` (For scripts/test_1094_config_pollution.sh)**:
  `"[PASS] test_1094_config_pollution passed successfully"`
