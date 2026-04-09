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
3. **参数化控制与持久化**：Yellow 重试限制 (N) 和 Red 重试限制 (M) 必须作为流水线可配置参数，且在部署升级中不被覆盖。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **配置优先级与持久化**: 
  - 引入 `config/sdlc_config.json.template` 作为分发模板。
  - 修改 `deploy.sh`：在执行原子交换前，检查生产环境是否存在 `sdlc_config.json`。若存在，则将其备份并恢复到新版本目录中（Hot-Preservation），防止 Boss 自定义的参数被升级覆盖。
- **spawn_planner.py / create_pr_contract.py**: 引入模板 Copy 逻辑。Planner 启动前，由脚本预先生成带有 YAML 头部的文件。
- **orchestrator.py (核心状态机重构)**:
  - 引入 `yellow_retry_limit (N)` 和 `red_retry_limit (M)` 参数。
  - **Yellow Path**: Review 失败时，`yellow_retry_count` 累加。若 < N，调用 `spawn_coder.py` 并传入 Feedback，保持 Session 不变，不执行 Git Reset。
  - **Red Path**: 若 `yellow_retry_count` 达到 N，则触发 Red Path。执行 `git reset --hard`，清空当前 Coder Session，`red_retry_count` 累加，`yellow_retry_count` 清零，开启全新会话重写。
  - **Black Path**: 若 `red_retry_count` 达到 M（即总计经历了 M * N 次 Review 失败），触发任务切分逻辑。
  - **计数器复位**: 任务切分（Micro-Slicing）后生成的新 PR 队列，其 M 和 N 计数器完全重新开始。
- **spawn_coder.py**: 增强 Session 管理。确保在 Yellow Path 下显式通过 `--session-id` 复用上下文。
- **回滚预案 (Rollback Plan)**: 
  - 依靠 `deploy.sh` 的原子备份机制。若新状态机失控，执行 `bash scripts/rollback.sh`。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 物理模板完整性**
  - **Given** 启动一个新的 PRD 分解任务。
  - **When** Planner 完成输出。
  - **Then** 所有生成的 PR 合约文件必须 100% 包含 `status: open` 头部。
- **Scenario 2: 配置热保留 (Hot Preservation)**
  - **Given** 已经手动修改了 `sdlc_config.json` 的 N 为 5。
  - **When** 执行 `bash deploy.sh` 进行系统升级。
  - **Then** 升级后的 `config/sdlc_config.json` 中的 N 依然保持为 5。
- **Scenario 3: Yellow Path 增量开发**
  - **Given** 一个 PR 初次 Review 失败。
  - **When** 失败次数 < N。
  - **Then** 系统不执行 `git reset`，Coder 能够基于当前代码修改。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **路径覆盖 E2E 测试 (`scripts/e2e/e2e_test_hierarchical_resilience.sh`)**:
  - **Green Test**: Mock Reviewer 返回 `APPROVED`，验证 PR 成功合并。
  - **Yellow-to-Green Test**: Mock Reviewer 先返回 `ACTION_REQUIRED`（1次），第二次返回 `APPROVED`。验证期间未发生 `git reset` 且 Session ID 保持一致。
  - **Yellow-to-Red Test**: 模拟连续 N 次 `ACTION_REQUIRED`。验证在第 N+1 次尝试前触发了 `git reset --hard` 并生成了新的 Session ID。
  - **Red-to-Black Test**: 模拟累计 $M \times N$ 次失败。验证系统最终调用了 `spawn_planner.py --slice-failed-pr` 触发任务熔断逻辑。
- **配置持久化测试**: 
  - 编写脚本模拟 `deploy.sh` 过程，断言本地配置文件在目录交换前后的内容一致性。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/orchestrator.py`
- `scripts/spawn_planner.py`
- `scripts/spawn_coder.py`
- `scripts/create_pr_contract.py`
- `deploy.sh`
- `config/prompts.json`
- `config/sdlc_config.json.template` (New File)

## 7. Hardcoded Content (硬编码内容声明)
- **参数名**: `YELLOW_RETRY_LIMIT`, `RED_RETRY_LIMIT`
- **Fallback 默认值**: N=3, M=2
- **PR 状态**: `status: open`, `status: in_progress`, `status: closed`, `status: superseded`
- **Review 判定**: `APPROVED`, `ACTION_REQUIRED`
- **路径标识**: `Green Path`, `Yellow Path`, `Red Path`, `Black Path`
- **错误代码**: `[FATAL_ESCALATION]`, `[DEAD_END]`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v1.0**: 确立分级防御路径。
- **v2.0 Revision**: 补全 Section 7 Hardcoded Content。
- **v3.0 Revision**: 引入配置 SSOT 与 M*N 数学逻辑，明确回滚预案。
- **v4.0 Revision**: 
  1. 增加了 `deploy.sh` 的 **Hot Preservation** 逻辑，解决 Boss 担心的配置覆盖问题。
  2. 详细定义了 **四色路径覆盖测试方案**，确保逻辑可被 Mock 验证。