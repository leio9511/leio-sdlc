---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix Hardcoded Paths in SKILL Documentation

## 1. Context & Problem (业务背景与核心痛点)
在前置的 `ISSUE-1132`（解除 OpenClaw 环境依赖）重构中，我们成功将代码逻辑从 `~/.openclaw/workspace/projects/...` 等硬编码的开发区路径中解绑。
但在对文档进行二次审计时，发现在供 Agent 运行时参考的静态说明书 `SKILL.md` 文件中，依然残留了致命的路径耦合：
1. **`skills/pm-skill/SKILL.md`**:
   - `init_prd.py` 的启动路径被硬编码为开发区绝对路径：`python3 ~/.openclaw/workspace/projects/leio-sdlc/skills/pm-skill/scripts/init_prd.py`。这会导致纯净环境下的 Gemini CLI 找不到文件。
2. **`SKILL.md` (leio-sdlc 主技能)**:
   - Orchestrator 的启动命令使用了相对路径：`python3 scripts/orchestrator.py`。当用户在任意外部项目目录（如 `~/my-app`）启动 Agent 时，执行此相对路径会导致 `File not found` 崩溃。

## 2. Requirements & User Stories (需求定义)
1. **通用安装路径约定**：更新所有的 `SKILL.md`，使其在文档层面遵守“全局技能安装点”（即 `~/.openclaw/skills/`）的约定，而非开发源码区。
2. **任意工作区兼容**：确保 Agent 在任何外部项目目录下执行 `pm-skill` 或 `leio-sdlc` 相关的 CLI 指令时，都能通过绝对路径成功调用脚本。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- 将 `skills/pm-skill/SKILL.md` 中的 `init_prd.py` 执行路径修改为正式安装路径下的绝对路径：
  `python3 ~/.openclaw/skills/pm-skill/scripts/init_prd.py`
- 将 `SKILL.md` 中的 Orchestrator 执行路径修改为正式安装路径下的绝对路径：
  `python3 ~/.openclaw/skills/leio-sdlc/scripts/orchestrator.py`
- 这是纯粹的文档层面（Prompt 指导）的静态修改，不涉及 Python 业务代码或单元测试的变动。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Agent 正确解析 PRD 生成命令。
  - **Given** Agent 阅读了 `pm-skill` 的 SKILL.md。
  - **When** 它试图执行 Scaffold 命令。
  - **Then** 执行的命令路径应为 `~/.openclaw/skills/pm-skill/scripts/init_prd.py`。
- **Scenario 2**: Agent 在外部工作区正确拉起管线。
  - **Given** Agent 在 `/tmp/external-app` 目录下。
  - **When** 收到启动 SDLC 的指令。
  - **Then** 它构造出的命令应以 `python3 ~/.openclaw/skills/leio-sdlc/scripts/orchestrator.py` 开头。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Review 断言**：本次提交不涉及单元测试变更。Reviewer 需验证两个 `SKILL.md` 文件中的指令示例已全部替换为指向 `~/.openclaw/skills/` 的绝对路径。

## 6. Framework Modifications (框架防篡改声明)
- `SKILL.md`
- `skills/pm-skill/SKILL.md`

## 7. Hardcoded Content (硬编码内容)
1. `skills/pm-skill/SKILL.md` 中：
   `python3 ~/.openclaw/skills/pm-skill/scripts/init_prd.py --project <Target_Project_Name> --title "<Short_Title>"`

2. `SKILL.md` 中：
   `python3 ~/.openclaw/skills/leio-sdlc/scripts/orchestrator.py --help`
