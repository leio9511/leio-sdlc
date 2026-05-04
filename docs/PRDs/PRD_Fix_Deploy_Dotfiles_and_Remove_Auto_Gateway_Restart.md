---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Fix Deploy Dotfiles and Remove Auto Gateway Restart

## 1. Context & Problem (业务背景与核心痛点)
`leio-sdlc` 的标准部署流程由三个脚本组成：`deploy.sh`、`kit-deploy.sh`、`skills/pm-skill/deploy.sh`。当前存在两个独立但影响部署正确性的问题：

### 问题 A：dotfiles 不被复制
`deploy.sh` 第 86 行使用：
```bash
cp -a .dist/* "$TMP_DIR/"
```
bash 的 `*` glob 默认不匹配以 `.` 开头的隐藏文件/目录。因此 `.sdlc_hooks/` 等点开头的文件和目录虽然存在于 workspace（被 git 跟踪）、也存在于 `.dist/`（被 build 阶段 rsync 包含），但不会通过 `cp` 的 `*` 被复制到 runtime。这导致：
- 新版 role-aware hook `.sdlc_hooks/pre-commit` 未被部署到 runtime
- `doctor.py` 找不到源 hook 文件，无法执行项目级 hook 安装

### 问题 B：deploy 默认重启 gateway
三个 deploy 脚本的末尾都有 `openclaw gateway restart`：
- `kit-deploy.sh` 第 16 行
- `deploy.sh` 第 144 行
- `skills/pm-skill/deploy.sh` 第 63 行

绝大多数脚本更新（Python 脚本、playbook、template、config）不需要重启 gateway。只有 `SKILL.md` 变更才需要 gateway 重新加载 skill 元数据。每次 deploy 都无条件触发 gateway restart 带来两个副作用：
1. **重启会误杀同时运行的其他 SDLC 子进程**（如 ISSUE-1180 中确认的跨 channel 静默杀进程问题）
2. **重启本身就是一次服务中断**，对无必要的场景属于多余的风险

---

## 2. Requirements & User Stories (需求定义)
### Functional Requirements
1. `deploy.sh` 中从 `.dist/` 复制文件到 runtime 的步骤，必须同时复制显式文件和隐藏文件（dotfiles）。
2. `kit-deploy.sh` 末尾的 `openclaw gateway restart` 必须移除。
3. `deploy.sh` 末尾的 `openclaw gateway restart` 必须移除。
4. `skills/pm-skill/deploy.sh` 末尾的 `openclaw gateway restart` 必须移除。
5. `deploy.sh` 中已存在的 `--no-restart` flag 语义必须保留为兼容占位；在自动重启逻辑被移除后，`--no-restart` 仍然允许传入，但不再改变最终行为（no-op）。
6. 三个脚本不得新增新的自动重启逻辑。
7. 本 PR 的主质量门禁必须是扩展后的 `scripts/test_deploy_hardcopy.sh`；手工验证只能作为补充确认，不得作为主放行依据。

### Non-Functional Requirements
1. 修复必须保持为**最小范围**：只修 dotfiles 复制和移除 gateway 重启，不改动其他部署逻辑（如 rsync、原子交换、备份、hot config preserve、Gemini link 等）。
2. 不新增新的配置文件或参数系统。
3. 不影响 `deploy.sh` 的 `--preflight` 和备份回滚机制。

### User Stories
- 作为运维者，我希望 deploy 成功后，所有被 git 跟踪的部署产物（包括 dotfiles）都能正确复制到 runtime。
- 作为运维者，我希望 deploy 不会自动重启 gateway，除非我明确需要并手动执行。
- 作为同时跑多条 SDLC 的用户，我不希望一次 deploy 顺手杀掉另一个正在跑的 pipeline。

---

## 3. Architecture & Technical Strategy (架构设计与技术路线)
### 3.1 Files in Scope
- `deploy.sh`：修复 dotfiles 复制 + 移除 gateway restart
- `kit-deploy.sh`：移除 gateway restart
- `skills/pm-skill/deploy.sh`：移除 gateway restart

### 3.2 Fix A: Dotfiles 复制
`deploy.sh` 第 86 行：
```bash
cp -a .dist/* "$TMP_DIR/"
```
必须收敛为一个**确定实现**，不允许给 coder 留二选一。唯一允许的修复方案是：
```bash
cp -a .dist/. "$TMP_DIR/"
```

选择这个方案的原因：
- 直接包含 dotfiles
- 不依赖 shell 全局状态（如 `dotglob`）
- 语义最直接，最不容易引入后续副作用

### 3.3 Fix B: 移除 gateway restart
完全删除三类脚本中的 `openclaw gateway restart` 调用块：

#### deploy.sh
删除第 144 行附近的 `openclaw gateway restart || echo ...` 块。

#### kit-deploy.sh
删除第 16 行附近的 `openclaw gateway restart || echo ...` 行。

#### skills/pm-skill/deploy.sh
删除第 63 行附近的 `openclaw gateway restart || true` 行。

### 3.4 Deployment Notes
本次修复部署后需**手动**执行 `openclaw gateway restart` 以加载新版 `SKILL.md`（如有变更）。后续正常 deploy 不再自动触发重启。

---

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1: dotfiles are deployed into runtime**
  - **Given** a mock build output under `.dist/` containing `.sdlc_hooks/pre-commit`
  - **When** `deploy.sh` stages and swaps the release into the runtime target
  - **Then** the runtime skill directory must contain `.sdlc_hooks/pre-commit`
  - **And** the deployed hook file content must match the source hook content

- **Scenario 2: deploy.sh does not restart gateway**
  - **Given** a mock `openclaw` binary on PATH that records invocations
  - **When** `deploy.sh` completes a deployment
  - **Then** no `openclaw gateway restart` invocation must be recorded

- **Scenario 3: kit-deploy.sh does not restart gateway**
  - **Given** a mock `openclaw` binary on PATH that records invocations
  - **When** `kit-deploy.sh` completes a deployment
  - **Then** no `openclaw gateway restart` invocation must be recorded

- **Scenario 4: pm-skill deploy does not restart gateway**
  - **Given** a mock `openclaw` binary on PATH that records invocations
  - **When** `skills/pm-skill/deploy.sh` completes a deployment
  - **Then** no `openclaw gateway restart` invocation must be recorded

- **Scenario 5: --no-restart remains accepted as a compatibility no-op**
  - **Given** the deploy script still accepts `--no-restart`
  - **When** `deploy.sh --no-restart` is executed
  - **Then** deployment must still succeed
  - **And** its runtime behavior must not differ from the default non-restarting flow

- **Scenario 6: existing deploy features still work**
  - **Given** a standard hard-copy deployment flow in isolated mock HOME
  - **When** deployment completes
  - **Then** backup creation, atomic swap, hot config preservation, Gemini link behavior, and GitHub sync compatibility must remain intact

---

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
核心质量风险：
1. **dotfiles 仍然未被部署** — 修复方案无效
2. **deploy 流程被破坏** — 删 gateway restart 时误伤了其他逻辑
3. **三条 deploy 路径行为不一致** — 主脚本修了，kit 或 pm-skill 子路径仍偷偷重启或遗漏 dotfiles
4. **`--no-restart` 被误删或语义漂移** — 老调用方兼容性受损

测试策略：
- **必须**扩展 `scripts/test_deploy_hardcopy.sh`，并把它作为本 PR 的主验收门禁。
- 测试必须运行在 `HOME_MOCK` 隔离环境中，不得依赖真实 runtime 目录。
- 测试必须使用 fake `openclaw` binary / invocation log 来验证是否触发了 `gateway restart`，而不是依赖人工观察。
- 手工 deploy 验证只作为补充确认，不作为主放行依据。
- 扩展后的 `scripts/test_deploy_hardcopy.sh` 至少必须覆盖：
  - dotfiles（特别是 `.sdlc_hooks/pre-commit`）被复制到 runtime
  - `deploy.sh` 不触发 `gateway restart`
  - `kit-deploy.sh` 不触发 `gateway restart`
  - `skills/pm-skill/deploy.sh` 不触发 `gateway restart`
  - `deploy.sh --no-restart` 仍成功且行为与默认非重启流一致
  - 原子交换、备份、hot config preserve、Gemini link 等既有行为不回归

质量目标：
- dotfiles 修复可在隔离环境中稳定复现
- 三条 deploy 路径的“无自动重启”行为可自动证明
- `--no-restart` 保持兼容
- deploy 核心逻辑改动在进入真实 runtime 前已经被隔离测试覆盖

---

## 6. Framework Modifications (框架防篡改声明)
本 PRD 明确授权修改以下框架文件：
- `deploy.sh`
- `kit-deploy.sh`
- `skills/pm-skill/deploy.sh`
- `scripts/test_deploy_hardcopy.sh`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初始设计，覆盖两个问题：dotfiles 复制修复 + 移除 gateway auto-restart。
- **Audit Rejection (v1.0)**: Auditor 认为对 deploy 核心底层逻辑的修改不能以手工验证为主；同时指出 dotfiles 修复方案存在二选一歧义，`--no-restart` 兼容语义也未被单独纳入 BDD。
- **v1.1 Revision Rationale**: 收紧为单一实现方案 `cp -a .dist/. "$TMP_DIR/"`，并把 `scripts/test_deploy_hardcopy.sh` 升级为强制主验收门禁；同时补齐三条 deploy 路径无自动重启、以及 `--no-restart` 兼容 no-op 的黑盒验收场景。

---

## 7. Hardcoded Content (硬编码内容)
None
