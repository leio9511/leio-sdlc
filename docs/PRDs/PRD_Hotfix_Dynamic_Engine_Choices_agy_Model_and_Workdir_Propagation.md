---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Hotfix_Dynamic_Engine_Choices_agy_Model_and_Workdir_Propagation

## 1. Context & Problem (业务背景与核心痛点)

PRD `Stateless_Direct_CLI_and_agy_Engine_Integration` (#64) 的实现已经完成并通过了 SDLC + preflight，说明 direct_cli stateless 化、generic renderer、agy 注册等主干已经落地。

但后续验证暴露了一个关键事实：**`--engine agy` 的入口放开并不等于 agy 真正可用。**

当前存在三个闭环缺口：

### Problem 1: `spawn_auditor.py` 和 `spawn_planner.py` 仍硬编码 `--engine` choices
`orchestrator.py` 与 `spawn_reviewer.py` 已经改为从 engine registry 动态读取用户面 engine alias，但 `spawn_auditor.py` 与 `spawn_planner.py` 仍然写死：

```python
choices=["openclaw", "gemini"]
```

这导致通过 config 注册的新引擎（如 `agy_direct_cli` / `cli_alias: "agy"`）虽然在 registry 和 generic renderer 层已经被支持，但操作者无法从这两个入口直接选择它。

### Problem 2: `agy_direct_cli` 的 `model_arg` 是错误合同
`config/engines.default.json` 中 `agy_direct_cli.execution.model_arg` 被写成：

```json
{"flag": "--model", "value": "{model}"}
```

但 `agy` CLI 不支持 `--model` 参数。模型选择应由 agy 自己的 profile/config 决定。这个错误来源于上游 PRD 对 agy CLI 行为的错误假设，generic renderer 只是忠实执行了该错误合同。

### Problem 3: direct_cli 的 `workspace_arg` / `{workdir}` 运行时合同未闭环
当前 `agent_driver.invoke_agent()` 将：
- prompt/stdout/stderr 的中间文件目录（`temp_dir`）
- SDLC artifact / state 目录（`run_dir`）
- direct_cli 的逻辑工作区（用于替换 `{workdir}`）

混在了一起。

具体表现是：
- 未传 `run_dir` 时，direct_cli 的 `{workdir}` 退化为 `tempfile.gettempdir()`，即 `/tmp`
- 传了 `run_dir` 时，direct_cli 的 `{workdir}` 被错误绑定为 `run_dir`

这对 Gemini 没有暴露问题，因为 Gemini 的 `workspace_arg = null`。但 agy 定义了：

```json
"workspace_arg": {"flag": "--add-dir", "value": "{workdir}"}
```

因此，如果不修，`agy` 在 auditor/planner/reviewer 等 direct_cli 调用点上可能被实际启动成：

```bash
agy --add-dir /tmp --print ...
```

或者被绑定到 `.sdlc_runs/...`，而不是锁定的项目根目录。

这不是 UI 层问题，而是 **runtime contract propagation** 问题。只要 `workspace_arg` 存在，`workdir` 就必须是强制合同，而不是可选 hint。

## 2. Requirements & User Stories (需求定义)

### FR-1: `spawn_auditor.py` 动态 engine choices
`spawn_auditor.py` 的 `--engine` 参数必须从 engine registry 动态读取用户面 alias，不再硬编码 `openclaw/gemini`。

### FR-2: `spawn_planner.py` 动态 engine choices
`spawn_planner.py` 同样必须从 engine registry 动态读取 `--engine` choices，不再硬编码。

### FR-3: `agy_direct_cli` 的 `model_arg` 修正为不传 model flag
`config/engines.default.json` 中 `agy_direct_cli.execution.model_arg` 必须改为 `null`，表示 generic renderer 不应对 agy 传递任何 `--model` 参数。

`default_model` 也必须改为 `null`，避免暗示 agy 在 CLI 层支持模型选择。

### FR-4: `invoke_agent()` 显式支持 direct_cli 的独立 `workdir`
`agent_driver.invoke_agent()` 必须新增显式 `workdir` 参数，用于 direct_cli 的 `{workdir}` 模板替换。

它必须把三类路径职责彻底分开：
- `temp_dir`：prompt/stdout/stderr 中间文件目录
- `run_dir`：SDLC artifact/state 目录
- `cli_workdir`：direct_cli 的逻辑工作区（用于 `workspace_arg` 渲染）

### FR-5: 对定义了 `workspace_arg` 的 direct_cli engine，缺失 `workdir` 必须 fail-closed
这是本 hotfix 的核心原则。

如果一个 direct_cli engine entry 定义了：
```json
"workspace_arg": { ... }
```
那么在调用 `invoke_agent()` 时：
- 若未显式提供 `workdir`
- 不允许退化为 `run_dir`
- 不允许退化为 `/tmp`
- 必须直接 FATAL

### FR-6: 所有 direct_cli 调用点必须遵守 `workdir` 强制合同
本 PRD 不接受“只修当前验证入口”的局部补丁。

至少以下 direct_cli 调用链必须显式审视并闭环：
- `spawn_auditor.py`
- `spawn_planner.py`
- `spawn_reviewer.py`

对这些入口而言：
- 若会通过 `invoke_agent()` 调用 direct_cli engine
- 且该 engine 定义了 `workspace_arg`
- 则必须显式传项目根 `workdir`

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Hotfix 定位

这是一个 **hotfix + runtime contract completion**，不是新架构设计。

它修补的是 #64 实现后的三个遗留缺口：
1. **入口层缺口**：`spawn_auditor.py` / `spawn_planner.py` 的 `--engine` 还没完全动态化
2. **配置层缺口**：agy `model_arg` 写错
3. **运行时合同缺口**：direct_cli 的 `{workdir}` 没被全链路、fail-closed 地正确传播

### 3.2 目标文件

| 文件 | 改动性质 | 说明 |
|------|----------|------|
| `scripts/agent_driver.py` | 微调 | `invoke_agent()` 新增显式 `workdir` 参数；解耦 `temp_dir` / `run_dir` / `cli_workdir`；对有 `workspace_arg` 的 direct_cli engine 缺失 `workdir` 时 FATAL |
| `scripts/spawn_auditor.py` | 微调 | 动态 engine choices；调用 `invoke_agent(..., run_dir=run_dir, workdir=workdir)` |
| `scripts/spawn_planner.py` | 微调 | 动态 engine choices；调用 `invoke_agent(..., run_dir=args.run_dir or out_dir, workdir=workdir)` |
| `scripts/spawn_reviewer.py` | 微调/审视 | 确保其 direct_cli 路径在需要时显式传入项目根 `workdir` |
| `config/engines.default.json` | 微调 | `agy_direct_cli.execution.model_arg -> null`；`default_model -> null` |

### 3.3 设计原则

1. **不重复发明 engine 选择逻辑**：`spawn_auditor.py` / `spawn_planner.py` 直接复用 `spawn_reviewer.py` 已有的 `load_engine_registry()` + `build_spawner_engine_choices()` 模式。
2. **不改变 generic renderer 的总体策略**：仍然由 engine config 决定命令行，只修正错误 contract 与 workdir 传播。
3. **不影响 OpenClaw native 路径**：OpenClaw 没有 `workspace_arg`，该 hotfix 不改变它的行为。
4. **fail-closed**：只要 direct_cli engine 定义了 `workspace_arg`，没有显式 `workdir` 就直接失败。
5. **不做局部补丁**：不能只让 auditor/planner 通过验证，而把 reviewer 或未来 direct_cli 调用点继续留在隐式 fallback 状态。

## 4. Acceptance Criteria (BDD 黑盒验收标准)

### Scenario 1: `spawn_auditor.py` 接受 `--engine agy`
- **Given** `agy_direct_cli` 已在 `config/engines.default.json` 中注册，且 `cli_alias = "agy"`
- **When** 操作者执行 `spawn_auditor.py --engine agy --prd-file <path> --workdir <repo-root> ...`
- **Then** argparse 接受 `agy` 为合法 choice
- **And** 审计流程可以进入 agy 调用阶段

### Scenario 2: `spawn_planner.py` 接受 `--engine agy`
- **Given** `agy_direct_cli` 已注册
- **When** 操作者执行 `spawn_planner.py --engine agy --prd-file <path> --workdir <repo-root> ...`
- **Then** argparse 接受 `agy` 为合法 choice
- **And** 规划流程可以进入 agy 调用阶段

### Scenario 3: `agy` 调用不传 `--model`
- **Given** `agy_direct_cli.execution.model_arg = null`
- **When** generic renderer 为 agy 组装命令
- **Then** 命令中不包含 `--model`
- **And** agy 不再因不支持 `--model` 而报错退出

### Scenario 4: `agy` 的 `--add-dir` 指向锁定项目根目录
- **Given** `agy_direct_cli.execution.workspace_arg = {"flag": "--add-dir", "value": "{workdir}"}`
- **When** 操作者执行 `spawn_auditor.py --engine agy --workdir /repo/root ...`
- **Then** 实际 agy 命令中包含 `--add-dir /repo/root`
- **And** 不得出现 `--add-dir /tmp`
- **And** 不得出现 `--add-dir <run_dir>`

### Scenario 5: 定义了 `workspace_arg` 的 direct_cli engine 在缺失 `workdir` 时 fail-closed
- **Given** 一个 direct_cli engine entry 定义了 `execution.workspace_arg`
- **When** 调用方执行 `invoke_agent()` 时未显式提供 `workdir`
- **Then** 进程直接 FATAL
- **And** 不得静默退化到 `/tmp`
- **And** 不得静默退化到 `run_dir`

### Scenario 6: Gemini engine 不受影响
- **Given** Gemini engine entry 保持不变
- **When** 操作者执行 `spawn_auditor.py --engine gemini ...`
- **Then** Gemini 仍然通过 generic direct_cli renderer 正常启动
- **And** `--model` 参数仍按 config 模板传入

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 核心质量风险
1. **argparse 重构错误**：registry 加载失败导致 `spawn_auditor.py` / `spawn_planner.py` 无法初始化。
2. **agy 参数错误残留**：`model_arg` 改为 `null` 后，仍可能有其他 CLI 参数错误。
3. **workspace 错位**：`--add-dir` 仍被渲染成 `/tmp` 或 `run_dir`。
4. **Partial Contract Propagation**：只修 auditor/planner 而 reviewer 或其他 direct_cli 路径继续走旧合同。

### Mock 策略
- 不要求真实网络访问。
- 可使用 mock agy CLI 来验证命令行参数。

### 测试分层
- **快速回归**：
  - `spawn_auditor.py --engine openclaw` 跑一次
  - `spawn_planner.py --engine openclaw` 跑一次
  - `spawn_reviewer.py --engine openclaw` 跑一次（或对应最小 smoke）
  确认动态 choices 与新 `workdir` 合同没有破坏现有入口
- **参数静态校验**：确认 `engines.default.json` 中 `agy_direct_cli.execution.model_arg == null`
- **黑盒 direct_cli 验证**：mock agy，断言命令行包含 `--add-dir <locked project root>`，且不包含 `--model`
- **fail-closed 验证**：对定义了 `workspace_arg` 的 direct_cli engine，在不传 `workdir` 时断言直接报 FATAL

### 下游质量信号
- `preflight.sh` 全部通过
- `test_engine_registry.py` 全部通过
- 与 `spawn_reviewer.py` 现有动态 engine 方案保持一致

## 6. Framework Modifications (框架防篡改声明)

- `scripts/agent_driver.py`：`invoke_agent()` 新增 `workdir` 参数，解耦 `temp_dir` / `run_dir` / `cli_workdir`；对定义了 `workspace_arg` 的 direct_cli engine 在缺失 `workdir` 时直接 FATAL
- `scripts/spawn_auditor.py`：动态 engine choices；显式传 `run_dir` 和 `workdir`
- `scripts/spawn_planner.py`：动态 engine choices；显式传 `run_dir` 和 `workdir`
- `scripts/spawn_reviewer.py`：审视并修正 direct_cli 路径，确保定义了 `workspace_arg` 的 engine 一定显式传 `workdir`
- `config/engines.default.json`：agy entry 中 `model_arg -> null`，`default_model -> null`

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)

- **v1.0**: 初始草案 (2026-05-27)。聚焦两个问题：`spawn_auditor.py` / `spawn_planner.py` 的动态 engine choices 以及 agy `model_arg` 修正。
- **Audit Rejection (v1.0)**: OpenClaw + GPT-5.5 auditor 指出 scope 误判为纯 argparse 修补，遗漏了 direct_cli 的 `workspace_arg` / `{workdir}` 运行时传播问题。
- **v1.1 Revision Rationale**: 将 hotfix scope 扩展为 3 项：dynamic engine choices、agy `model_arg` 修正、`invoke_agent()` 显式 `workdir` 传播，并补充 `--add-dir <locked project workdir>` 的黑盒验收标准。
- **Audit Rejection (v1.1)**: Auditor 进一步指出不能只修 auditor/planner 两个入口；一旦 `workdir` 被提升为 direct_cli 的核心运行时合同，就必须全链路 fail-closed，不能继续允许任何 direct_cli 路径静默退化到 `/tmp` 或 `run_dir`。
- **v1.2 Revision Rationale**: 将 hotfix 升级为完整的 runtime contract completion：`workdir` 对定义了 `workspace_arg` 的 direct_cli engine 成为强制合同；缺失时直接 FATAL，并将 reviewer 纳入修复范围。 

---

## 7. Hardcoded Content (硬编码内容)

### 7.1 `spawn_auditor.py` / `spawn_planner.py` / `spawn_reviewer.py` — 新增 import

- **Insert after existing runtime imports:**
```python
from engine_registry import load_engine_registry, build_spawner_engine_choices
```

### 7.2 `spawn_auditor.py` / `spawn_planner.py` — engine registry 加载

- **Insert before `parser = argparse.ArgumentParser(...)`:**
```python
    SDLC_ROOT = os.path.dirname(current_dir)
    engine_reg = load_engine_registry(SDLC_ROOT)
    dynamic_choices, engine_alias_map, default_engine = build_spawner_engine_choices(engine_reg)
```

### 7.3 `spawn_auditor.py` — `--engine` argparse 替换

- **Replace:**
```python
    parser.add_argument("--engine", choices=["openclaw", "gemini"], default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE), help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})")
```
- **With:**
```python
    parser.add_argument("--engine", choices=dynamic_choices, default=default_engine, help=f"Execution engine to use for the agent driver (default: {default_engine})")
```

### 7.4 `spawn_planner.py` — `--engine` argparse 替换

- **Replace:**
```python
    parser.add_argument("--engine", choices=["openclaw", "gemini"], default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE), help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})")
```
- **With:**
```python
    parser.add_argument("--engine", choices=dynamic_choices, default=default_engine, help=f"Execution engine to use for the agent driver (default: {default_engine})")
```

### 7.5 `spawn_auditor.py` / `spawn_planner.py` — `--model` help 文案更新

- **Replace (both files):**
```python
    parser.add_argument("--model", default=os.environ.get("SDLC_MODEL", config.DEFAULT_GEMINI_MODEL), help=f"Model to use when --engine is gemini (default: {config.DEFAULT_GEMINI_MODEL})")
```
- **With:**
```python
    parser.add_argument("--model", default=os.environ.get("SDLC_MODEL", config.DEFAULT_GEMINI_MODEL), help=f"Model override for the selected engine (default: {config.DEFAULT_GEMINI_MODEL})")
```

### 7.6 `agent_driver.py` — `invoke_agent()` 签名扩展

- **Replace function signature:**
```python
def invoke_agent(task_string, session_key=None, role=None, run_dir=None, thinking: str | None = None):
```
- **With:**
```python
def invoke_agent(task_string, session_key=None, role=None, run_dir=None, workdir=None, thinking: str | None = None):
```

### 7.7 `agent_driver.py` — `temp_dir` / `cli_workdir` 解耦并 fail-closed

- **Replace:**
```python
if run_dir and os.path.exists(run_dir):
    temp_dir = os.path.join(run_dir, ".tmp")
    workdir = run_dir
else:
    temp_dir = tempfile.gettempdir()
    workdir = temp_dir
```
- **With:**
```python
if run_dir and os.path.exists(run_dir):
    temp_dir = os.path.join(run_dir, ".tmp")
else:
    temp_dir = tempfile.gettempdir()

execution = engine_spec.get("execution", {}) if isinstance(engine_spec, dict) else {}
workspace_arg = execution.get("workspace_arg") if isinstance(execution, dict) else None
if engine_spec.get("runtime_mode") == "direct_cli" and workspace_arg and not workdir:
    print("[FATAL] direct_cli engine with workspace_arg requires explicit workdir", file=sys.stderr)
    sys.exit(1)

cli_workdir = workdir or temp_dir
```

### 7.8 `agent_driver.py` — direct_cli 命令组装调用修正

- **Replace:**
```python
engine_spec, secure_msg, workdir, model
```
- **With:**
```python
engine_spec, secure_msg, cli_workdir, model
```

### 7.9 `spawn_auditor.py` — `invoke_agent()` 调用修正

- **Replace:**
```python
result = invoke_agent(task_string, session_key=session_id, role="auditor", thinking=resolved_thinking)
```
- **With:**
```python
result = invoke_agent(task_string, session_key=session_id, role="auditor", run_dir=run_dir, workdir=workdir, thinking=resolved_thinking)
```

### 7.10 `spawn_planner.py` — `invoke_agent()` 调用修正

- **Replace:**
```python
result = invoke_agent(task_string, session_key=session_id, role="planner", thinking=resolved_thinking)
```
- **With:**
```python
result = invoke_agent(task_string, session_key=session_id, role="planner", run_dir=args.run_dir or out_dir, workdir=workdir, thinking=resolved_thinking)
```

### 7.11 `spawn_reviewer.py` — direct_cli 路径 workdir 传播要求

- **Requirement:** any `invoke_agent()` call path that can route to a direct_cli engine with `workspace_arg` defined MUST pass explicit `workdir=workdir`.

- **Exact fatal string for missing workdir contract:**
```python
"[FATAL] direct_cli engine with workspace_arg requires explicit workdir"
```

### 7.12 `config/engines.default.json` — `agy_direct_cli` model 字段修正

- **Replace in `agy_direct_cli.execution`:**
```json
"model_arg": {"flag": "--model", "value": "{model}"},
```
- **With:**
```json
"model_arg": null,
```

- **Replace:**
```json
"default_model": "auto"
```
- **With:**
```json
"default_model": null
```
