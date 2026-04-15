---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix Remaining Hardcoded OpenClaw Paths and CLI Dependencies

## 1. Context & Problem (业务背景与核心痛点)
在前续的 `ISSUE-1132` (环境解耦 Phase 1) 中，我们解除了主流程脚本和文档对 `~/.openclaw` 的强依赖。
然而经过深度审计，系统中仍存在 3 类漏网的硬编码路径和命令：
1. **回滚脚本失效**：`rollback.sh` (含 `pm-skill` 下的) 依然强行拼装 `OPENCLAW_DIR="$HOME_DIR/.openclaw"` 寻找发布历史，并在末尾毫无防护地调用 `openclaw gateway restart`。在纯净环境下执行降级会导致崩溃。
2. **交互提示误导**：`orchestrator.py`、`doctor.py` 和 Git hooks (`.sdlc_hooks/pre-commit`) 在报错打印提示时，硬编码了 `python3 ~/.openclaw/skills/leio-sdlc/scripts/...`，导致在自定义安装点（如 `$SDLC_SKILLS_ROOT` 或 `~/.gemini/skills/`）的用户复制执行时报错 `File not found`。
3. **老旧测试脚本脆性**：部分 Bash E2E 测试（如 `test_077_spawn_auditor.sh`, `test_033_cleanup_deprecated.sh`）在 Setup 阶段写死了从 `/root/.openclaw/workspace/projects/leio-sdlc/*` 拷贝文件，阻碍了在任意工作区开发 SDLC 框架自身。

## 2. Requirements & User Stories (需求定义)
1. **可靠的通用降级**：回滚脚本能够动态识别全局安装目录，优雅处理并兼容非 OpenClaw 环境。
2. **准确的环境感知提示**：系统在抛出包含命令路径的帮助提示时，必须动态拼接当前真实的安装点路径，不再误导用户。
3. **测试环境自适应**：所有的 Bash 单元测试和 E2E 测试均通过相对路径（如 `$(dirname "$0")/..`）定位工程根目录，解除对 `workspace/projects` 的绝对绑定。

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **`rollback.sh` 修复**：
  引入与部署脚本一致的 `command -v openclaw` 嗅探逻辑。将写死的 `OPENCLAW_DIR` 替换为可通过环境变量（`$SDLC_SKILLS_ROOT` 或回退至 `~/.openclaw/skills`）配置的路径计算。
- **动态路径交互提示**：
  在 `orchestrator.py`, `doctor.py` 和 `setup_logging.py` 中，使用此前引入的 `config.SDLC_SKILLS_ROOT` 变量来动态生成打印在 stdout 中的帮助指令字符串。
  修改 `.sdlc_hooks/pre-commit` 中的硬编码，允许其跟随环境上下文。
- **测试解耦**：
  使用 Bash 原生的 `cd "$(dirname "$0")/.."` 逻辑替代在 `test_*.sh` 中的绝对路径 `cp` 指令。

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: 纯净环境下安全回滚。
  - **Given** 环境中没有 `openclaw` 且技能安装在 `~/.gemini/skills/`。
  - **When** 触发 `rollback.sh`。
  - **Then** 脚本正确定位历史目录并完成本地恢复，跳过 gateway 重启且不崩溃。
- **Scenario 2**: 动态生成帮助指令。
  - **Given** 触发一个业务阻断错误（如缺少 `commit_state.py` 落盘）。
  - **When** 控制台抛出 `[FATAL]` 提示。
  - **Then** 提示中的命令路径使用已解析的动态根目录而非固定的 `~/.openclaw`。
- **Scenario 3**: 外部工作区运行测试套件。
  - **Given** 在 `/tmp/leio-sdlc-clone` 中开发。
  - **When** 执行 `test_077_spawn_auditor.sh`。
  - **Then** 测试在沙盒内正确 Setup 源码并全绿通过。

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
切分为 3 个原子的 Micro-PRs 进行安全重构：
1. **PR-001**: 修复 `rollback.sh` 和 `.sdlc_hooks/pre-commit`，加入命令嗅探与动态路径（独立验证无破坏性）。
2. **PR-002**: 修复 `orchestrator.py` 和 `doctor.py` 内部的 `stdout` 错误提示字符串，使用 `SDLC_SKILLS_ROOT` 动态拼接。同步修复涉及断言这些硬编码字符串的单元测试。
3. **PR-003**: 修复 `tests/test_077_spawn_auditor.sh` 和 `tests/test_033_cleanup_deprecated.sh` 等包含开发区绝对路径的测试脚本。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/rollback.sh`
- `skills/pm-skill/rollback.sh`
- `.sdlc_hooks/pre-commit`
- `scripts/orchestrator.py`
- `scripts/doctor.py`
- `tests/test_077_spawn_auditor.sh`
- `tests/test_033_cleanup_deprecated.sh`

## 7. Hardcoded Content (硬编码内容)

必须在代码中严格使用以下模板化字符串（配合 `config.SDLC_SKILLS_ROOT` 或环境变量注入使用）以取代硬编码的 `~/.openclaw/skills/...`：

1. **`scripts/orchestrator.py` (Uncommitted files error):**
   `f"[FATAL] Workspace contains uncommitted state files. You MUST baseline your PRD and state using the official gateway: python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py --files <path>"`

2. **`scripts/orchestrator.py` & `scripts/doctor.py` (SDLC compliant error):**
   `f'[FATAL] Project is not SDLC compliant. Please run "python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/doctor.py --fix" to apply the required infrastructure.'`

3. **`.sdlc_hooks/pre-commit` (Bash 错误提示):**
   `"python3 ${SDLC_SKILLS_ROOT:-~/.openclaw/skills}/leio-sdlc/scripts/commit_state.py --files <path_to_files>"`

4. **`skills/pm-skill/rollback.sh` & `scripts/rollback.sh` (环境变量回退):**
   `OPENCLAW_DIR="${SDLC_SKILLS_ROOT:-${HOME_MOCK:-$HOME}/.openclaw/skills}"`
   且包含嗅探网关重启的逻辑：
   ```bash
   if command -v openclaw >/dev/null 2>&1; then
       echo "🔄 Restarting OpenClaw gateway..."
       openclaw gateway restart || echo "⚠️ Gateway restart failed or not available."
   fi
   ```
