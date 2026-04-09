---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1088_Hierarchical_SDLC_Failure_Resilience

## 1. Context & Problem (业务背景与核心痛点)
当前 leio-sdlc 引擎存在两个关键脆弱点：
1. **Planner 模板漂移**：Planner Agent 在生成 PR 合约时经常遗漏 `status: open` 头部，导致 Orchestrator 误判任务已完成，产生空转。
2. **粗暴的重试机制**：Review 失败后，系统会立即执行 `git reset --hard` 并清空会话。这种“掀桌子重来”的逻辑摧毁了 Coder 已有的工作成果，不符合增量开发的常识。

## 2. Requirements & User Stories (需求定义)
1. **物理模板增强**：Planner 通过 `create_pr_contract.py` 生成文件。修改该脚本，使其在合并 Planner 输出时，强制套用 `TEMPLATES/PR_Contract.md.template` 的头部，Planner 仅需提供业务内容。
2. **四级路径防御体系 (Four-Path Resilience)**：
   - **Green (顺利完成)**: Review 通过 -> 正常 Merge。
   - **Yellow (增量修正)**: Review 失败 -> 在同一个 Coder Session 中读取 Feedback 继续修改，**严禁** Reset 代码 (重试上限 N)。
   - **Red (物理换人)**: 连续 N 次 Yellow 失败 -> 执行 `git reset --hard`，开启**全新**的 Coder Session 从零重写 (重试上限 M)。
   - **Black (任务熔断)**: 连续 M 次 Red 失败 -> 判定为任务粒度或架构问题。打回 Planner 重新切分任务（Micro-Slicing）。如果无法切分，则退出并报告 Boss。
3. **异常处理整合**：将现有的“超时 (Timeout)”、“仲裁失败 (Arbitration Reject)”等逻辑统一编入 Red Path 或相应的失败计数中。
4. **参数化控制与持久化**：Yellow 重试限制 (N) 和 Red 重试限制 (M) 必须作为流水线可配置参数，且在部署升级中不被覆盖。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 模板控制
- **create_pr_contract.py**: 维持原有的 `calculate_index` 命名算法。增加“模板合并”逻辑：读取 `PR_Contract.md.template` 的前 2 行（含 status），然后拼接 Planner 传入的 Content。

### 3.2 状态机重构 (orchestrator.py)
**原逻辑 vs 新逻辑映射表：**

| 场景 | 原有处理方式 | 新版四色路径处理方式 |
| :--- | :--- | :--- |
| Review 失败 | 1-4 次: 直接重试 (Session 模糊) / 5 次: 仲裁 | **Yellow Path**: 同 Session 增量修正，不 Reset (重试 N 次) |
| 仲裁失败 | 进入 State 5 (Reset) | **Red Path**: `git reset` + 换 Session |
| 超时 (Timeout) | 进入 State 5 (Reset) | **Red Path**: 物理重置现场，换人重写 |
| 重试累计失败 | State 5 循环 3 次后切片 | **Black Path**: 累计 $M \times N$ 次失败后切片 |

### 3.3 配置与部署
- **Hot Preservation**: 修改 `deploy.sh`。升级前备份 `config/sdlc_config.json`，交换目录后恢复。若不存在，则从 `.template` 初始化。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 物理模板完整性**
  - **Given** Planner 调用 `create_pr_contract.py`。
  - **When** 脚本生成 PR 文件。
  - **Then** 文件名应符合 `PR_00X_...` 规范，且文件头必须包含 `status: open`。
- **Scenario 2: 配置热保留**
  - **Given** 手动修改了 `sdlc_config.json` 的 N 为 5。
  - **When** 执行 `bash deploy.sh`。
  - **Then** 升级后的参数依然为 5。
- **Scenario 3: 路径演进逻辑**
  - **Given** 一个 PR 持续失败。
  - **Then** 必须观察到：前 N 次不发生 `git reset`；第 N+1 次发生物理重置；总计 $M \times N$ 次后触发 Planner 切片。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **专项测试脚本**: `scripts/e2e/e2e_test_hierarchical_resilience.sh`
- **验证重点**: 
  1. 验证 Coder 是否收到了包含 Review Feedback 的增量 Prompt。
  2. 验证 Red Path 触发时，`.coder_session` 标识符是否发生了更新（即“换人”）。
  3. 验证超时场景是否能正确损耗一次重试机会并触发相应的重置逻辑。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py` (核心重构)
- `scripts/spawn_coder.py` (Session 生命周期管理)
- `scripts/create_pr_contract.py` (模板强制合并)
- `deploy.sh` (配置保护逻辑)
- `config/prompts.json` (Prompt 降噪)

## 7. Hardcoded Content (硬编码内容声明)
- **参数名**: `YELLOW_RETRY_LIMIT`, `RED_RETRY_LIMIT`
- **默认值**: N=3, M=2
- **PR 状态**: `status: open`, `status: in_progress`, `status: closed`, `status: superseded`
- **Review 判定**: `APPROVED`, `ACTION_REQUIRED`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0-v4.0**: 完善防御路径、配置保护与测试方案。
- **v5.0 Revision**: 
  1. 明确 PR 文件名由 `create_pr_contract.py` 的原有逻辑指定，确保命名连续性。
  2. 明确将“超时”、“仲裁”等原散落逻辑统一收编进 Red Path。
  3. 增加了“新旧逻辑映射表”，确保重构过程中不丢失原有的健壮性逻辑。