---
Affected_Projects: [leio-sdlc]
---

# PRD: Unified Dual-Deployment Architecture (OpenClaw & Gemini CLI)

## 1. Context & Problem (业务背景与核心痛点)

在实施 Gemini CLI 原生部署方案（V1）时，引入了一个分离的 `scripts/gemini-deploy.sh` 脚本。这种设计导致了以下问题：
1. **代码冗余**：`gemini-deploy.sh` 的很多逻辑与原有的 `deploy.sh` 重复。
2. **部署割裂**：用户需要判断当前环境，决定运行哪个部署脚本。
3. **架构偏离**：无论是 OpenClaw 还是 Gemini CLI，运行时都需要一个本地的物理副本。专门为 Gemini CLI 维护一套独立的目录和部署流程是多余的。

**目标**：消除 `gemini-deploy.sh`，将其核心的"技能注册"逻辑统一收口到现有的 `deploy.sh` 流程中，实现**"一次部署，双边生效"（Dual-Compatibility）**的架构。

## 2. Requirements & User Stories (需求定义)

- **FR-1**: 彻底删除冗余的 `scripts/gemini-deploy.sh` 文件及其相关测试（`tests/test_gemini_deploy.sh`）。
- **FR-2**: 在现有的 `deploy.sh` 中增加环境探测机制。如果目标系统安装了 `gemini` 命令行工具，则自动执行 `gemini skills link` 将当前部署好的运行时目录注册为 Gemini CLI 技能。
- **FR-3**: 确保这种"探测并注册"的逻辑同样适用于随主项目部署的 `skills/pm-skill/deploy.sh`，使 pm-skill 也能双环境兼容。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 统一收口到 deploy.sh
原来的部署流程主要负责 Hard Copy、Hot Preservation 以及重启 OpenClaw Gateway。
现在在 `deploy.sh` 流程的最末尾增加"Dual-Compatibility Link"环节：

```bash
# 判断是否存在 gemini CLI 命令
if command -v gemini >/dev/null 2>&1; then
    # 如果存在，将 $PROD_DIR 软链接到用户的 Gemini CLI 技能库中
    gemini skills link "$PROD_DIR"
fi
```
这样，如果环境里只有 Gemini CLI（没有 OpenClaw），它也会自动完成技能挂载。

### 3.2 移除历史遗留代码
由于采用了统一架构，之前为了隔离 `gemini-deploy.sh` 而加在 `.release_ignore` 和相关测试排除逻辑的代码可以完全删除，降低系统的维护成本。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### Scenario 1: OpenClaw 专属环境（无 Gemini CLI）
- **Given** 一台安装了 OpenClaw 但**没有安装** `gemini` 的机器
- **When** 运行 `deploy.sh`
- **Then** 部署成功，跳过 Gemini link 步骤，重启 OpenClaw gateway

### Scenario 2: Gemini CLI 双重环境
- **Given** 一台同时安装了 OpenClaw 和 `gemini` 的机器
- **When** 运行 `deploy.sh`
- **Then** 部署成功，执行了 `gemini skills link` 注册，并重启 OpenClaw gateway

### Scenario 3: 彻底移除冗余脚本
- **Given** 合并完成后的 master 分支
- **When** 搜索代码库
- **Then** 不存在 `scripts/gemini-deploy.sh`，并且 `.release_ignore` 移除了对其的过滤规则

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

- **脚本覆盖率**：重构 `tests/test_deploy_hardcopy.sh` 测试用例，增加 mock `gemini` 命中与未命中的验证场景。
- **回归测试**：运行全部 E2E 测试，保证基础的部署原子化能力和回滚功能不被破坏。

## 6. Framework Modifications (框架防篡改声明)

- `deploy.sh` — 追加 Gemini CLI 探测与 link 注册逻辑。
- `skills/pm-skill/deploy.sh` — 同步追加 Gemini CLI 探测与 link 注册逻辑。
- `scripts/gemini-deploy.sh` — **删除**。
- `tests/test_gemini_deploy.sh` — **删除**。
- `.release_ignore` — 移除针对 `scripts/gemini-deploy.sh` 的排除行。

## 7. Hardcoded Content (硬编码内容)

### 在 deploy.sh 和 skills/pm-skill/deploy.sh 的结尾处追加以下逻辑（在执行 Gateway Reload 前或后均可）：

```bash
    # 8. Gemini CLI Dual-Compatibility Link
    if command -v gemini >/dev/null 2>&1; then
        echo "🔗 Gemini CLI detected. Linking skill for dual compatibility..."
        gemini skills link "$PROD_DIR" || echo "⚠️ Gemini link failed, but deployment succeeded."
    fi
```

### 从 `.release_ignore` 中删除以下两行：
```text
scripts/gemini-deploy.sh
tests/test_gemini_deploy.sh
```