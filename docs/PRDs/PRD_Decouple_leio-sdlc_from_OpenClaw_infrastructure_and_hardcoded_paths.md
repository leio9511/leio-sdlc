---
Affected_Projects: [leio-sdlc]
---

# PRD: Decouple leio-sdlc from OpenClaw infrastructure and hardcoded paths

## 1. Context & Problem (业务背景与核心痛点)
目前系统存在“基础设施绑架”和“工作区路径绑架”，导致它只能在 OpenClaw 的特定目录里运行：
1. **基础设施绑架**：脚本强依赖 `openclaw` CLI，如果在新机器上仅安装了 `gemini cli`，在发送 Slack 通知 (`agent_driver.py`) 或执行部署 (`kit-deploy.sh`, `deploy.sh`) 时会因为找不到命令而崩溃。
2. **工作区路径绑架**：脚本中充斥着防测试死锁的硬编码拦截（如 `if "/root/.openclaw/workspace/projects/" in __file__`），且部分逻辑（如 `init_prd.py` 和 并发锁机制）写死了必须在 `~/.openclaw/workspace` 下运行。这导致无法对任意本地代码库启动 SDLC 管线。

## 2. Requirements & User Stories (需求定义)
1. **基础设施优雅降级 (Graceful Degradation)**：在没有任何 OpenClaw 程序的裸机上（仅有 Gemini CLI），部署与执行全流程都能平滑跑通，不会引发异常退出。
2. **工作区自由 (Workdir Freedom)**：保持技能脚本安装在全局约定的 `~/.openclaw/skills/`（或 `SDLC_SKILLS_ROOT`），但目标工作区 (`workdir`) 可以是系统中的任意合法目录。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **API 与 CLI 降级处理**：
  - `agent_driver.py` (`notify_channel`)：通过 `shutil.which("openclaw")` 嗅探，无则降级为 `logger.info("[Channel Message] ...")`。
  - `kit-deploy.sh` & `deploy.sh`：部署脚本通过 `command -v openclaw` 检查，不存在则跳过 `openclaw gateway restart`。
- **动态路径与模板注入 (Dynamic Routing & Templating)**：
  - 将 `config/prompts.json` 中的绝对路径替换为模板变量 `{SDLC_SKILLS_ROOT}`。在运行时由 Orchestrator 动态渲染。
- **解除硬编码与防护墙 (Relax Guards)**：
  - 全面移除 `spawn_*.py`, `orchestrator.py`, `init_prd.py` 中的 `[FATAL_STARTUP]` 硬编码路径拦截逻辑。
  - `pm-skill/scripts/init_prd.py`：废除写死的 `workspace_root`，改为接受 `--workdir` 参数或默认使用 `os.getcwd()`。生成的文件落入 `workdir/docs/PRDs/`。
  - `orchestrator.py`：并发锁 (`lock_dir`) 从 `~/.openclaw/workspace/locks` 剥离，改为通过 `tempfile.gettempdir()` 或基于 `global-dir` 动态生成。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: 缺少 `openclaw` CLI 时，不崩溃。
  - **Given** 环境中没有 `openclaw` 命令。
  - **When** Orchestrator 尝试发送 channel message 或执行 deploy。
  - **Then** 系统优雅降级（打印日志 / 仅执行本地 link），进程继续，不抛出异常。
- **Scenario 2**: 在任意外部工作区运行。
  - **Given** 工作区在 `/tmp/my-app`。
  - **When** 运行 `spawn_orchestrator.py` 或 `init_prd.py`。
  - **Then** 脚本正常启动，不在控制台抛出 `[FATAL_STARTUP]` 拦截。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
为控制爆炸半径，重构将被强制切分为 **3 个原子的 Micro-PRs**。Coder 必须在同一个 PR 内同步修正对应的测试，保持 100% 绿色 CI：

1. **PR-001: 基础设施降级 (API/CLI 解耦)**
   - 修改 `agent_driver.py`, `deploy.sh`, `kit-deploy.sh` 增加嗅探。无破坏性，独立提测。
2. **PR-002: Prompt 模板化与单元测试修正**
   - 将 `config/prompts.json` 中的绝对路径改为 `{SDLC_SKILLS_ROOT}`。
   - **必须同步修复**：`tests/test_handoff_prompter.py` 和 `tests/test_handoff_prompts.py` 中的断言逻辑。
3. **PR-003: 移除绝对路径防线与修复 Bash 测试 (攻坚战)**
   - 删除所有 `spawn_*.py` 等脚本里的硬编码路径拦截。重构 `init_prd.py` 路径依赖。
   - **必须同步修复**：直接删除 `scripts/test_spawn_scripts_paths.py`。修改所有 bash 测试 (`scripts/test_*.sh`) 中硬编码的 Setup 路径。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/agent_driver.py`
- `scripts/orchestrator.py`
- `scripts/config.py`
- `skills/pm-skill/scripts/init_prd.py`
- `skills/pm-skill/deploy.sh`
- `scripts/kit-deploy.sh`
- `config/prompts.json`
- `tests/*` (涉及断言的单元测试及 bash e2e 测试)

## 7. Hardcoded Content (硬编码内容)
N/A
