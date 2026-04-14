---
Affected_Projects: [leio-sdlc]
---

# PRD: Gemini CLI Native Deployment for leio-sdlc (V1)

> ⚠️ **V1 免责声明**：本版本采用纯 `--yolo` 模式，无命令过滤机制，存在 AI 幻觉生成危险命令的风险。V2（详见 ISSUE-1126）将引入 Policy Engine 分层安全控制。

---

### ⚠️ Boss Mandate

**We want to build V1 as an OpenClaw Agent equivalent.** Since OpenClaw's native Agent is effectively running in YOLO mode (i.e., all tool calls are auto-approved without human confirmation), we intentionally accept the same behavior for the Gemini CLI Agent.

**Security enhancement is deferred to V2 (ISSUE-1126).** The purpose of this PRD is to detach leio-sdlc from the OpenClaw dependency, enabling a standalone Gemini CLI-based workflow. If you need stronger security guarantees, please wait for V2 or implement your own sandboxed environment.

## 1. Context & Problem (业务背景与核心痛点)

**目标**：在仅有 Gemini CLI 的空白 Linux 机器上，无需安装任何 OpenClaw 依赖，即可驱动完整的 leio-sdlc 流水线（PRD 生成 → Auditor 审核 → Orchestrator 执行）。

**现状**：
- leio-sdlc 当前的 `agent_driver.py` 默认调用 `openclaw agent` 来调度子任务。
- 如果目标机器没有安装 OpenClaw，流水线将直接崩溃。
- 但 `agent_driver.py` 已经预留了 `LLM_DRIVER=gemini` 分支，只需要激活并完善它即可。

**研究结论（基于 geminicli.com 官方文档）**：
- Gemini CLI 的 Skill 格式与 OpenClaw 几乎一致（都是 `SKILL.md` + `scripts/` 目录结构）。
- Gemini CLI 通过 `gemini -p "prompt"` 命令调度子任务，支持原生 `--model` 参数。
- leio-sdlc 的 `orchestrator.py` 是纯 Python 脚本，可以在任何有 Python 3.10+ 的机器上独立运行。

## 2. Requirements & User Stories (需求定义)

- **FR-1**: 创建一个 `gemini-deploy.sh` 部署脚本，在目标机器上安装 leio-sdlc 和 pm-skill，不依赖 OpenClaw。
- **FR-2**: 增强 `agent_driver.py`，当 `LLM_DRIVER=gemini` 时，通过 `gemini -p "task"` 命令调度子任务。
- **FR-3**: 确保 leio-sdlc 和 pm-skill 的 `SKILL.md` 与 Gemini CLI 格式兼容（YAML frontmatter）。
- **FR-4**: 提供清晰的环境变量配置（`SDLC_MODEL`, `GEMINI_API_KEY` 等），供用户在部署时设置。
- **FR-5**: Gemini 分支必须使用 `--yolo` 参数（**Boss 明确要求**），保证在无头环境（Headless/CI）下执行敏感命令时无需人类交互确认，防止流水线永久挂起死锁。
**FR-6（V2）**：配合 Gemini CLI Policy Engine 的分角色 blacklist/whitelist 机制（见 ISSUE-1126）。V1 暂不实现。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 部署层：gemini-deploy.sh
- 将 leio-sdlc + pm-skill 克隆/复制到用户指定目录（如 `~/sdlc-kit/`）。
- 创建 Gemini CLI 所需的 Skill 软链接或路径配置。
- 生成环境变量模板文件 `.sdlc_env` 供用户配置 API Key。
- **不依赖 OpenClaw Gateway**，纯 shell + git + python3。

### 3.2 调度层：agent_driver.py 的 Gemini 分支

**⚠️ `--yolo` 参数是 Boss 明确要求的 Feature（来自 leio 的业务需求）**
目的：确保 Gemini CLI Agent 在执行敏感命令时不会弹出交互式确认（Y/n），从而避免自动化流水线在无头环境（Headless/CI）中永久挂起死锁。

在无头自动化环境中，`gemini` 默认会在执行敏感操作时弹出交互式确认（Y/n）。若不加 `--yolo`，orchestrator 将永远挂起等待人类响应，导致流水线死锁。

### 3.3 V2 规划：Policy Engine 分层安全（见 ISSUE-1126）

V1 采用纯 yolo 模式，无命令过滤。V2 将引入基于 Gemini CLI Policy Engine 的分角色安全策略（Auditor/Reviewer 用 Whitelist，Coder 用 Blacklist）。

### 3.4 README 风险声明（V1 必须）

**WARNING**: V1 uses pure `--yolo` mode without command filtering. This means:
- AI hallucinations may generate dangerous commands (e.g., `rm -rf /`)
- No built-in protection against destructive operations
- User is solely responsible for assessing risk before deployment

Users should consider:
1. Running in a sandboxed environment (Docker/VM)
2. Using git shallow clones to limit blast radius
3. Upgrading to V2 (ISSUE-1126) once available

当前代码已有：
```python
if llm_driver == "gemini":
    model = os.environ.get("TEST_MODEL", "google/gemini-2.0-flash")
    cmd_exec = resolve_cmd("gemini")
    cmd = [cmd_exec, "--yolo", "-p", secure_msg]
```

需要增强为：
- 支持 `SDLC_MODEL` 环境变量（优先级最高）。
- 支持传入 `--model` 参数。
- **保留 `--yolo`**，将 `secure_msg`（任务描述）作为 `gemini -p` 的 prompt。

### 3.5 技能层：SKILL.md 兼容性（向下兼容 OpenClaw）

**⚠️ 关键要求：YAML frontmatter 修改不得破坏 OpenClaw 原生兼容性**
leio-sdlc 和 pm-skill 需同时支持 OpenClaw 和 Gemini CLI 两个运行环境。SKILL.md 的 YAML frontmatter 调整必须在两个平台下均可正常解析，不得引入破坏性变更。
检查并优化现有的 `SKILL.md` 文件，确保：
- YAML frontmatter 在文件最顶部（无空行）。
- `description` 字段清晰，能让 Gemini CLI 在会话启动时正确识别和注入。

### 3.6 编排层：Orchestrator 独立运行
- `orchestrator.py` 是纯 Python 脚本，可直接用 `python3 orchestrator.py ...` 启动。
- Gemini CLI 的会话作为"管理器"，通过 prompt 与 orchestrator 交互。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### Scenario 1: gemini-deploy.sh 成功部署
- **Given** 一台仅有 Python 3.10+ 和 Git 的 Linux 机器
- **When** 执行 `bash gemini-deploy.sh --target-dir ~/sdlc-kit/`
- **Then** leio-sdlc 和 pm-skill 被正确安装，`GEMINI_API_KEY` 模板文件被创建

### Scenario 2: agent_driver 使用 Gemini 调度
- **Given** 环境变量 `LLM_DRIVER=gemini` 且 `SDLC_MODEL=google/gemini-3-flash-preview`
- **When** orchestrator 调用 `spawn_coder` 时
- **Then** 实际执行的命令为 `gemini -p "task description" --model google/gemini-3-flash-preview`

### Scenario 3: Gemini CLI 识别 leio-sdlc Skill
- **Given** 用户在 `~/sdlc-kit/` 启动了 Gemini CLI 会话
- **When** 用户说"用 leio-sdlc 跑一个 PRD"
- **Then** Gemini CLI 自动识别并激活 leio-sdlc skill，注入对应的系统提示词

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **隔离测试**：在无 OpenClaw 的 Docker 容器中执行 `gemini-deploy.sh`，验证全链路部署。
- **Mock 测试**：mock `gemini` 命令，验证 `agent_driver.py` 是否生成正确的子任务命令。
- **集成测试**：在干净 Linux VM 上启动完整流水线（PRD 生成 → Auditor → Orchestrator）。

## 6. Framework Modifications (框架防篡改声明)

- `scripts/agent_driver.py` — 增强 Gemini 分支，支持 SDLC_MODEL 环境变量透传，**必须保留 `--yolo` 参数**
- `SKILL.md` — 微调 YAML frontmatter，**确保与 Gemini CLI 和 OpenClaw 双方兼容**
- `scripts/gemini-deploy.sh` — 新增，用于独立部署（不在 OpenClaw 体系内）
- `~/.gemini/policies/sdlc.toml` — **V2 提供**（V1 由用户自行决定是否配置）

## 7. Hardcoded Content (硬编码内容)

### gemini-deploy.sh 部署脚本骨架：
```bash
#!/bin/bash
set -e
TARGET_DIR="${1:-$HOME/sdlc-kit}"
echo "Deploying leio-sdlc to $TARGET_DIR..."
# 1. Clone or copy leio-sdlc
# 2. Create .sdlc_env template
# 3. Print setup instructions
```

### agent_driver.py Gemini 分支增强（Section 7 完整硬编码）：
```python
if llm_driver == "gemini":
    model = os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL", "google/gemini-2.0-flash")
    cmd_exec = resolve_cmd("gemini")
    # --yolo is CRITICAL: prevents interactive Y/n prompt blocking in headless/CI environments
    # NOTE: This is a Boss-required feature to ensure the pipeline never hangs waiting for human input
    # Security in V1 is equivalent to OpenClaw Agent (yolo mode, no command filtering)
    # V2 (ISSUE-1126) will add Policy Engine-based command filtering
    cmd = [cmd_exec, "--yolo", "-p", task_string, "--model", model]
```
