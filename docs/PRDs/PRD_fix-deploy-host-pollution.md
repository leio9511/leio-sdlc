---
Affected_Projects: [leio-sdlc]
Context_Workdir: /usr/local/google/home/lychen/Projects/leio-sdlc
---

# PRD: fix-deploy-host-pollution

## 1. Context & Problem (业务背景与核心痛点)

在引入 Gemini CLI 双向兼容部署机制（通过 `deploy.sh` 自动执行 `gemini skills link`）之后，出现了一个严重的集成问题：
当开发者在本地运行 Python E2E/集成测试时，测试框架会拉起一个临时沙箱目录（`/tmp/deploy-isolation-XXXXXX`）并设置 `HOME_MOCK` 来隔离部署目录。然而，由于测试环境没有完全隔离标准的 `$HOME` 环境变量，导致部署脚本中调用的**真实 `gemini` 命令行工具**依然使用真实的 `$HOME`。

这导致真实的 `~/.gemini/skills/` 目录下的软链接被篡改，指向了临时的测试沙箱目录。测试结束后，临时目录被删除，导致开发者的真实开发环境遗留了失效的断链（broken symlinks）。

我们需要彻底隔离测试运行期的 `HOME` 逃逸，确保测试的绝对 hermetic（密闭性），不污染宿主机环境。

## 2. Requirements & User Stories (需求定义)

- **FR-1**: 部署脚本（`deploy.sh` 和 `skills/pm-skill/deploy.sh`）在调用 `gemini skills link` 时，必须显式绑定当前部署的 `HOME_ROOT`，确保在 `HOME_MOCK` 激活时，链接注册在 mock home 中。
- **FR-2**: 测试隔离助手（`tests/deploy_test_support.py` 中的 `isolated_repo_env`）必须将标准的 `HOME` 环境变量显式重写为 `mock_home`，防止任何子进程/宿主工具（如未 mock 的 `gemini`）逃逸沙箱。
- **Non-Regression**: 确保此项隔离不会破坏现有的 Git 隔离测试或其他依赖 Git 局部配置的 E2E 测试。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

我们采用**双重防御（Defense in Depth）**策略：

### 3.1 部署脚本防御 (Option A)
在 `deploy.sh` 和 `skills/pm-skill/deploy.sh` 中，通过前缀环境变量强制重定向 `gemini` 的 `HOME`：
```bash
HOME="$HOME_ROOT" gemini skills link "$PROD_DIR" --consent
```
因为 `HOME_ROOT` 在生产环境等于 `$HOME`，在测试环境等于 `$HOME_MOCK`，这保证了双环境下的绝对行为一致性与安全性。

### 3.2 测试环境防御 (Option B)
在 Python E2E 测试的通用隔离上下文管理器 `isolated_repo_env` 中，除了注入 `HOME_MOCK` 之外，同步重写 `env["HOME"]` 为 `mock_home`。
这能够为所有在测试期间由 `subprocess` 派生的子进程提供最底层的密闭沙箱保护。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: Real User Deployment (生产部署行为不受影响)**
  - **Given** 用户在真实宿主环境下运行 `./deploy.sh` 或 `bash skills/pm-skill/deploy.sh`
  - **When** `gemini` 命令行工具可用
  - **Then** 技能被正确软链接到真实的 `~/.gemini/skills/`
  - **And** 软链接指向真实的 `~/.openclaw/skills/` 目录

- **Scenario 2: Python Test Execution Isolation (测试彻底隔离不污染宿主)**
  - **Given** 运行 `pytest tests/` 集成测试
  - **When** 测试调用 `deploy.sh` 并触发 `gemini skills link`
  - **Then** 真实的宿主目录 `~/.gemini/skills/` **不发生任何改变**（没有新链接，旧链接不被篡改）
  - **And** 软链接只会被创建在临时沙箱内（例如 `/tmp/deploy-isolation-XXXXXX/home/.gemini/skills/`）

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **质量风险**: 更改 `env["HOME"]` 可能会影响某些依赖全局 `~/.gitconfig` 的 Git 操作测试。但我们的 `setup_sandbox.sh` 中已经包含 `git config --local` 局部身份注入，因此风险极低。
- **验证手段**:
  1. 运行全部部署相关的 pytest 测试：`pytest tests/test_deploy_*.py`
  2. 运行 bash 集成测试：`bash scripts/test_deploy_hardcopy.sh`
  3. **宿主环境对比验证**：在运行测试前后，通过 `ls -la ~/.gemini/skills` 确认没有新增或篡改任何链接。

## 6. Framework Modifications (框架防篡改声明)

以下核心框架文件已被授权修改以实现本 PRD 的安全策略：
- `deploy.sh` — 绑定 `gemini` 执行期的 `HOME`。
- `skills/pm-skill/deploy.sh` — 同步绑定 `gemini` 执行期的 `HOME`。
- `tests/deploy_test_support.py` — 注入 `env["HOME"]` 到隔离环境中。

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
*Strictly for historical tracking. Planner and Coder must ignore.*

- **v1.0**: 针对测试污染宿主环境的 symlink 泄露问题，提出部署脚本重定向与测试上下文完全隔离的双重修复方案。

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
