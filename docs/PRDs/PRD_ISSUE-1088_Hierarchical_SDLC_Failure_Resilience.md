---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1088_Hierarchical_SDLC_Failure_Resilience

## 1. Context & Problem (业务背景与核心痛点)
当前 leio-sdlc 引擎在 PR 生成和重试机制上存在设计缺陷：
1. **Planner 模板失控**：PR 合约头部（如 `status: open`）由 Planner Agent 全量生成，导致头部信息经常缺失，产生流水线空转。
2. **重试机制单一**：无论失败原因，系统均采取“硬重置 + 丢弃会话”的策略，摧毁了 Coder 的增量工作成果。

## 2. Requirements & User Stories (需求定义)
1. **Scaffold-then-Fill (初始化即契约)**：参考 `init_prd.py` 逻辑。Planner 生成 PR 时，必须先调用工具生成带有标准头部的 PR 骨架文件，然后再填充具体内容。**物理上将“管理元数据（status）”与“业务内容（Objective/Scope）”解耦。**
2. **四级路径防御体系 (Four-Path Resilience)**：
   - **Green**: 直接过审合并。
   - **Yellow (增量)**: Review 失败但次数 < N -> 在原 Session 增量修改，**不准** Reset。
   - **Red (换人)**: 连续 N 次 Yellow 失败 -> 执行 `git reset --hard` 并**物理换 Session ID**，模拟“换个新人重写”。
   - **Black (熔断)**: 连续 M 次 Red 失败 -> 任务打回 Planner 二次切分。无法切分则向 Boss 报警。
3. **参数化控制**：N (Yellow Limit) 和 M (Red Limit) 需在配置文件中可调，且部署不丢失。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 模板生成工作流 (Scaffolding Flow)
- **旧流程**：Planner (思考) -> 生成全量 Markdown -> 调用脚本写入。
- **新流程**：
  1. Planner (思考切分) -> 调用 `create_pr_contract.py --title "..." --only-scaffold`。
  2. 脚本计算 PRID，Copy 模板，注入 `status: open` 和标题，**直接在 job 目录下创建文件**。
  3. 脚本将文件路径返回给 Planner。
  4. Planner 使用 `edit` 填充具体章节。
- **物理保障**：如果 Planner 试图通过 `write` 覆盖整个文件，Orchestrator 将在 State 1 进行强制检测，若缺少 `status` 头部则判定为非法 PR。

### 3.2 状态机重构 (orchestrator.py)
- 引入 `yellow_counter` 和 `red_counter`。
- 修改 `Yellow Path`：移除 `git reset --hard` 动作。
- 修改 `Red Path`：显式更新 `.coder_session` 里的 ID，确保下一次 `spawn_coder.py` 启动一个干净的 context。
- 整合超时、仲裁逻辑进入 Red Path。

### 3.3 部署与配置保护
- **Hot Preservation**: `deploy.sh` 升级时，优先保护 `config/sdlc_config.json` 不被 `.dist` 覆盖。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: 物理模板强绑定**
  - **When** Planner 完成切分。
  - **Then** PR 文件的第一行必须是 `status: open`，且该行不是由 Planner “写”出来的，而是由初始化脚本“带”出来的。
- **Scenario 2: 会话延续性**
  - **Given** Yellow Path 触发。
  - **Then** Coder 必须能看到上一个回合自己写的代码，严禁出现代码被清空的情况。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **E2E 压力测试**: 模拟一个 PR 连续 6 次被拒（N=3, M=2），验证系统是否经历了：3次增量修改 -> 1次物理重置 -> 3次增量修改 -> 1次任务切分。

## 6. Framework Modifications
- `scripts/orchestrator.py`
- `scripts/create_pr_contract.py` (新增 --only-scaffold 模式)
- `scripts/spawn_coder.py` (Session 生命周期管理)
- `deploy.sh` (Hot Preservation)
- `config/prompts.json` (移除干扰性指令)

## 7. Hardcoded Content
- `YELLOW_RETRY_LIMIT` (N), `RED_RETRY_LIMIT` (M)
- `APPROVED`, `ACTION_REQUIRED`
- `status: open`, `status: in_progress`

---

## Appendix: Architecture Evolution Trace
- **v1.0-v5.0**: 定义路径、映射逻辑、配置保护。
- **v6.0 Revision**: 
  1. 响应 Boss 疑问：明确 PR 生成逻辑为“初始化脚本定名定头 -> Planner 填空”，彻底剥夺 Planner 修改 `status` 的物理机会。
  2. 明确在“切分之前”还是“之后”：Planner 思考完切分方案后，第一步动作就是调用工具 Scaffold 出所有 PR 骨架，拿到路径后再逐个填充内容。
