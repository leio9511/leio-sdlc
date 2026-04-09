---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1088_Hierarchical_SDLC_Failure_Resilience

## 1. Context & Problem (业务背景与核心痛点)
当前 leio-sdlc 引擎存在两个关键脆弱点：
1. **Planner 模板漂移**：Planner Agent 在生成 PR 合约时经常遗漏 `status: open` 头部，导致 Orchestrator 误判任务已完成，产生空转。
2. **粗暴的重试机制**：Review 失败后，系统会立即执行 `git reset --hard` 并清空会话。这种“掀桌子重来”的逻辑摧毁了 Coder 已有的工作成果，不符合增量开发的常识。

## 2. Requirements & User Stories (需求定义)
1. **物理模板增强**：参考 PRD 初始化逻辑，由脚本先 Copy 模板并注入 PRID 占位符，Planner 只负责“填空”，从物理层面确保 `status` 头部存在。
2. **四级路径防御体系 (Four-Path Resilience)**：
   - **Green (顺利完成)**: Review 通过 -> 正常 Merge。
   - **Yellow (增量修正)**: Review 失败 -> 在同一个 Coder Session 中读取 Feedback 继续修改，**严禁** Reset 代码 (重试上限 N)。
   - **Red (物理换人)**: 连续 N 次 Yellow 失败 -> 执行 `git reset --hard`，开启**全新**的 Coder Session 从零重写 (重试上限 M)。
   - **Black (任务熔断)**: 连续 M 次 Red 失败 -> 判定为任务粒度或架构问题。打回 Planner 重新切分任务（Micro-Slicing）。如果无法切分，则退出并报告 Boss。
3. **参数化控制**：Yellow 重试限制 (N) 和 Red 重试限制 (M) 必须作为流水线可配置参数。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **spawn_planner.py / create_pr_contract.py**: 引入模板 Copy 逻辑。Planner 启动前，由脚本预先生成带有 YAML 头部的文件。
- **orchestrator.py**: 核心重构。重写 State 3-4-5 的循环逻辑，引入 `yellow_retry_count` 和 `red_retry_count` 计数器，精准控制 Reset 触发时机。
- **spawn_coder.py**: 增强 Session 管理。确保在 Yellow Path 下显式通过 `--session-id` 复用上下文。
- **config/prompts.json**: 优化 Planner Prompt，移除“严禁修改 status”等带有干扰性的指令，改为引导式填空。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 物理模板完整性**
  - **Given** 启动一个新的 PRD 分解任务。
  - **When** Planner 完成输出。
  - **Then** 所有生成的 PR 合约文件必须 100% 包含 `status: open` 头部。
- **Scenario 2: Yellow Path 增量开发**
  - **Given** 一个 PR 初次 Review 失败。
  - **When** 进入重试循环。
  - **Then** `git status` 应显示之前的修改依然存在，且 Coder 能够看到 Review Feedback。
- **Scenario 3: Red Path 物理重置**
  - **Given** 一个 PR 连续失败次数超过 N。
  - **When** 触发下一次重试。
  - **Then** 系统必须执行 `git reset --hard`，且 Coder 应该像一个“新员工”一样从干净的代码库开始。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Mock 驱动测试**：必须编写 E2E 测试脚本，通过 Mock Reviewer 连续返回 `ACTION_REQUIRED`，验证 Orchestrator 是否能精准地在第 N 次失败时执行 Reset，在第 N+M 次失败时触发 Black Path。
- **核心风险**：防止在 Yellow Path 下 Coder 陷入死循环。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_coder.py`
- `scripts/create_pr_contract.py`
- `config/prompts.json`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 按照 Boss 指示，确立 Green/Yellow/Red/Black 四级防御路径，并将模板生成逻辑从模型自发改为脚本物理驱动。