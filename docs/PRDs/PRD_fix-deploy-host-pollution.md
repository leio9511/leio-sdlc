---
Affected_Projects: [leio-sdlc]
Context_Workdir: /usr/local/google/home/lychen/Projects/leio-sdlc
---

# PRD: fix-deploy-host-pollution

## 1. Context & Problem (业务背景与核心痛点)

我们在 `leio-sdlc` 的部署与运行期管道中发现了两个关键的集成缺陷（Integration Bugs），它们分别破坏了测试环境的密闭性（Hermeticity）以及多引擎环境下的参数传递（Engine Propagation）：

### Bug 1: E2E 测试污染宿主环境 (`~/.gemini/skills` 链接篡改)
在引入 Gemini CLI 双向兼容部署机制（通过 `deploy.sh` 自动执行 `gemini skills link`）之后：
当开发者在本地运行 Python E2E/集成测试时，测试框架会拉起一个临时沙箱目录（`/tmp/deploy-isolation-XXXXXX`）并设置 `HOME_MOCK` 来隔离部署目录。然而，由于测试环境没有完全隔离标准的 `$HOME` 环境变量，导致部署脚本中调用的**真实 `gemini` 命令行工具**依然使用真实的 `$HOME`。这导致真实的 `~/.gemini/skills/` 目录下的软链接被篡改，指向了临时的测试沙箱目录。测试结束后临时目录被删除，导致开发者的真实开发环境遗留了失效的断链（broken symlinks）。

### Bug 2: 引擎参数传递失效 (子 Agent 强制覆盖为 `openclaw`)
当用户通过 `--engine agy`（或 `gemini`）显式指定非默认引擎启动 `orchestrator.py` 时，编排器会将引擎注入到环境变量 `LLM_DRIVER` 中并启动子进程。但是，由于 `orchestrator.py` 没有在命令行参数中显式向下透传 `--engine`，而子 Agent（`spawn_planner.py` 和 `spawn_coder.py`）的 `argparse` 将 `--engine` 的默认值硬编码为注册表中的静态默认值（`"openclaw"`），且没有回退到 `LLM_DRIVER` 环境变量。这导致子 Agent 在解析命令行时拿到默认值 `"openclaw"`，并看到其与环境中的 `"agy"` 不一致，从而**强行覆盖重写** `os.environ["LLM_DRIVER"] = "openclaw"`，最终导致子 Agent 调用已不存在的 `openclaw` 二进制而发生崩溃（FileNotFoundError）。

我们必须在一次修复中同时解决这两个阻碍多引擎稳定运行的硬伤。

## 2. Requirements & User Stories (需求定义)

- **FR-1**: 部署脚本（`deploy.sh` 和 `skills/pm-skill/deploy.sh`）在调用 `gemini skills link` 时，必须显式绑定当前部署的 `HOME_ROOT`，确保在 `HOME_MOCK` 激活时，链接注册在 mock home 中。
- **FR-2**: 测试隔离助手（`tests/deploy_test_support.py` 中的 `isolated_repo_env`）必须将标准的 `HOME` 环境变量显式重写为 `mock_home`，防止任何子进程/宿主工具（如未 mock 的 `gemini`）逃逸沙箱。
- **FR-3**: 子 Agent（`spawn_planner.py` 和 `spawn_coder.py`）必须在其 `argparse` 参数解析中，将 `--engine` 的默认值设定为 `os.environ.get("LLM_DRIVER", default_engine)`。这使得它们能够如同处理 `--model` (`SDLC_MODEL`) 一样，优雅地从父环境继承编排引擎，避免粗暴覆盖。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 针对 Bug 1 的双重防御 (Defense in Depth)
* **部署脚本防御**: 在 `deploy.sh` 和 `skills/pm-skill/deploy.sh` 中，强制 `gemini` 命令运行在 `$HOME_ROOT` 下：
  ```bash
  HOME="$HOME_ROOT" gemini skills link "$PROD_DIR" --consent
  ```
* **测试上下文隔离**: 在 `isolated_repo_env` 中注入 `env["HOME"] = str(mock_home)`。这为子进程（即使未直接处理 `HOME_MOCK` 的工具）提供了最底层的密闭沙箱保障。

### 3.2 针对 Bug 2 的继承防御 (Implicit Inheritance)
子 Agent 作为独立入口，其 CLI 参数解析应当与环境契约保持一致。我们不采用在 `orchestrator.py` 中到处拼装 `--engine` 的命令传递方案，而是采用与 `--model` 对齐的成熟模式：让子 Agent 的 `--engine` 默认值优先读取 `LLM_DRIVER` 环境变量，不存在时才回退到注册表的 default 别名。
这既保持了 `orchestrator.py` 的简洁度，又使子 Agent 具备了独立拉起时的环境适应性。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Real User Deployment (生产部署行为不受影响)**
  - **Given** 用户在真实宿主环境下运行 `./deploy.sh` 或 `bash skills/pm-skill/deploy.sh`
  - **When** `gemini` 命令行工具可用
  - **Then** 技能被正确软链接到真实的 `~/.gemini/skills/`
  - **And** 软链接指向真实的 `~/.openclaw/skills/` 目录

- **Scenario 2: Python Test Execution Isolation (测试彻底隔离不污染宿主)**
  - **Given** 运行 `pytest tests/` 集成测试
  - **When** 测试调用 `deploy.sh` 并触发 `gemini skills link`
  - **Then** 真实的宿主目录 `~/.gemini/skills/` **不发生任何改变**
  - **And** 软链接只会被创建在临时沙箱内（例如 `/tmp/deploy-isolation-XXXXXX/home/.gemini/skills/`）

- **Scenario 3: Engine Propagation (引擎参数完美向下传递)**
  - **Given** 运行 `orchestrator.py --engine agy` 启动编排器
  - **When** 编排器派生 `spawn_planner.py` 或 `spawn_coder.py` 子进程且未在 CLI 显式指定 `--engine`
  - **Then** 子进程将默认引擎解析为 `agy`（通过继承 `LLM_DRIVER`）
  - **And** 子进程不重写 `os.environ["LLM_DRIVER"]` 为 `openclaw`
  - **And** 子进程成功使用 `agy` 驱动执行规划/编码任务，而不触发 `openclaw` 二进制找不到的异常

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **验证手段**:
  1. 运行全部部署相关的 pytest 测试：`pytest tests/test_deploy_*.py`
  2. 运行 bash 集成测试：`bash scripts/test_deploy_hardcopy.sh`
  3. **引擎连通性测试**：使用 `--engine agy` 和 `--engine gemini` 启动本地沙箱运行，确保子 Agent 不发生 openclaw 崩溃。
  4. **宿主环境对比验证**：在运行测试前后，通过 `ls -la ~/.gemini/skills` 确认没有新增或篡改任何链接。

## 6. Framework Modifications (框架防篡改声明)

以下核心框架文件已被授权修改以实现本 PRD 的安全策略：
- `deploy.sh` — 绑定 `gemini` 执行期的 `HOME`。
- `skills/pm-skill/deploy.sh` — 同步绑定 `gemini` 执行期的 `HOME`。
- `tests/deploy_test_support.py` — 注入 `env["HOME"]` 到隔离环境中。
- `scripts/spawn_planner.py` — 修改 `--engine` 默认值读取 `LLM_DRIVER` 环境变量。
- `scripts/spawn_coder.py` — 修改 `--engine` 默认值读取 `LLM_DRIVER` 环境变量。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
*Strictly for historical tracking. Planner and Coder must ignore.*

- **v1.0**: 针对测试污染宿主环境的 symlink 泄露问题，提出部署脚本重定向与测试上下文完全隔离的双重修复方案。
- **v2.0**: 合并解决多引擎运行时，子 Agent argparse 默认值覆盖 `LLM_DRIVER` 导致 native 崩溃的引擎传播 bug。

---

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

#### For `deploy.sh` (around line 166):
```diff
-        gemini skills link "$PROD_DIR"  --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
+        HOME="$HOME_ROOT" gemini skills link "$PROD_DIR"  --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
```

#### For `skills/pm-skill/deploy.sh` (around line 76):
```diff
-    gemini skills link "$PROD_DIR" --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
+    HOME="$HOME_ROOT" gemini skills link "$PROD_DIR" --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
```

#### For `tests/deploy_test_support.py` (around line 129):
```diff
         env = os.environ.copy()
         env["HOME_MOCK"] = str(mock_home)
+        env["HOME"] = str(mock_home)
```

#### For `scripts/spawn_planner.py` (around line 29):
```diff
-    parser.add_argument("--engine", choices=dynamic_choices, default=default_engine, help=f"Execution engine to use for the agent driver (default: {default_engine})")
+    parser.add_argument("--engine", choices=dynamic_choices, default=os.environ.get("LLM_DRIVER", default_engine), help=f"Execution engine to use for the agent driver (default: {default_engine})")
```

#### For `scripts/spawn_coder.py` (around line 679):
```diff
-        default=default_engine,
+        default=os.environ.get("LLM_DRIVER", default_engine),
```
