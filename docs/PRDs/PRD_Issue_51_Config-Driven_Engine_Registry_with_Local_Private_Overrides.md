---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Issue 51 Config-Driven Engine Registry with Local Private Overrides

## 1. Context & Problem (业务背景与核心痛点)
在 `leio-sdlc` 过去的设计中,执行引擎(如 Gemini direct CLI, OpenClaw-native runtime)的信息与能力属性往往隐含地编码在主程序驱动文件(`scripts/agent_driver.py`、`scripts/orchestrator.py` 等)中。这种模式由于将引擎注册逻辑、元数据信息与运行选路强行绑定,造成了以下核心痛点:

1. **配置硬编码**: 无法无痛且不修改代码地新增、注销一个执行引擎,或在不破坏默认能力面假设的前提下动态表达其能力边界。
2. **私有/公司内部细节泄漏风险**: 私有/公司专有 CLI 或内部 ACP adapter 的名称、二进制执行路径、定制参数、独占会话标识等敏感细节极易在无隔离的情况下被提交进公共仓库。
3. **合同与配置脱节**: 随着 Issue #49 确立了严格的审计架构与收紧的 ACP continuation 语义,系统需要一种正式、声明式的手段将这些审计所得的能力状态(如 `authoritative_resume` / `unsupported`)持久化为控制面可读取的配置元数据。
4. **测试与运行隔离困难**: 如果没有可插拔、可覆写的本地注册配置入口,测试环境与真实私有环境无法安全使用不同的底层 adapter 指向。

本 PRD 的目标是建立一个**配置驱动的执行引擎注册表层 (Config-Driven Engine Registry)**。该层必须基于双层配置架构:
- **公共默认配置 (`config/engines.default.json`)**: 随代码库分发,公开表达符合通用规范的默认公共引擎信息(如 Gemini direct CLI、OpenClaw-native)。
- **本地私有覆写 (`config/engines.local.json`)**: 在 `.gitignore` 中声明,允许本地开发者或企业集成商动态添加、覆盖或扩展其特有的私有 ACP 引擎,完全避免泄漏任何专有命令、接口或秘钥到公共 repo。

本 PRD 明确强调以下定位与守门规则:
- **这是配置表达层 (Registry Layer),不是执行选路层 (Routing Layer)**: 本 issue 只负责引擎配置结构的设计、解析、合并、合同校验与防泄漏脱敏,绝对不负责在主 driver (`agent_driver.py`) 中实现真实的 ACP 调度与路由选路分支(那是后续 #52 的职责)。
- **严格与 #49 合同对齐**: 本注册表在解析与校验引擎能力时,必须强制执行 #49 已收紧的 ACP 续航二元语义、句柄获取模式等约束。

## 2. Requirements & User Stories (需求定义)

### 2.1 Functional Requirements
1. **双层文件配置加载**: 系统必须提供一个配置加载器,优先读取项目内置的公共默认注册表 `config/engines.default.json`,若本地存在 `config/engines.local.json`,则必须在内存中执行合规的合并(Merge)操作。
2. **本地覆写隔离性**: 本地私有覆写文件 `config/engines.local.json` 必须在仓库的 `.gitignore` 中声明,禁止提交进 git 历史。
3. **空配置安全容错**: 
   - 当本地没有 `config/engines.local.json` 时,加载器必须能够优雅工作,使用内置默认公共引擎正常启动。
   - 缺少私有配置不得导致任何公共默认引擎的加载与可用性中断。
4. **严格的合同校验 (Schema Validation)**: 
   - 合并后的引擎配置结构必须通过轻量级校验,其包含的元数据字段与值域必须严格限制在 #49 所确立的 contract 约束中。
   - 特别是 `continuity_mode` 必须只能取值于: `authoritative_resume` 或 `unsupported`。
   - `handle_acquisition_strategy` 必须只能取值于: `protocol_native`、`explicit_returned_handle` 或 `unavailable`。
   - 任何不符合上述合同约束的引擎配置加载均须被明确拦截并抛出解析异常,绝对禁止静默接受不合规配置。
5. **Private 敏感字段物理隔离**:
   - 只有本地私有注册表 `config/engines.local.json` 可以包含敏感或环境特异的执行参数(如 `executable_path`、`launch_arguments`、`custom_env_vars`、`private_endpoint`、`launch_command` 等)。
   - 公共默认注册表 `config/engines.default.json` 只允许包含公开、通用的能力声明,绝不能出现企业或环境专有的敏感路径与命令。
6. **配置解析层脱敏机制 (Redaction Discipline)**:
   - 当加载、合并或校验本地配置发生异常(如 JSON 语法错误、合同不合规、未授权值等)时,抛出的错误日志和 Traceback 中必须对本地私有覆写的敏感路径(如绝对路径、私有二进制文件名)进行物理脱敏。
   - 敏感字段在异常、错误信息、日志以及测试断言中必须被统一替换为 `[REDACTED]` 占位符。
7. **可测试输出要求**: 
   - 系统必须在仓库内交付针对配置加载、合并、校验、空配置兼容性、敏感字段脱敏等关键行为的高覆盖率自动化测试。
   - 测试和 fixtures 必须全部使用通用的 placeholder (如 `fake-private-cli`) 表达私有引擎,绝对禁止在代码库、测试文件、静态 sample 中泄露真实私有命令、敏感绝对路径。
8. **职责边界锁死**:
   - 本 issue 只负责 `scripts/config.py` (或新增独立模块如 `scripts/engine_registry.py`) 的配置设计、解析和合并逻辑。
   - 绝对不授权修改 `scripts/agent_driver.py`、`scripts/orchestrator.py` 的主执行路由分支,不授权真实拉起任何新增的私有引擎。
9. **同一 `engine_id` 的本地覆写语义必须固定为 field-level shallow merge**:
   - 本地 `config/engines.local.json` 中与默认 `engine_id` 同名的条目,必须以 default entry 为 base 执行字段级浅合并,本地字段优先覆盖。
   - 未在本地覆写中声明的字段,必须继承 default entry。
   - 本 issue 明确禁止把同名 engine entry 的本地覆写实现为整条记录全量替换。
10. **配置加载返回结构必须固定**:
   - `load_engine_registry(sdlc_root)` 的对外返回值必须是顶层包含 `engines` 键的完整 registry object,而不是直接返回裸 engine dictionary。
11. **每个 engine entry 的最小必填字段必须固定**:
   - `engine_id`
   - `display_name`
   - `runtime_mode`
   - `registration_visibility`
   - `continuity_mode`
   - `handle_acquisition_strategy`
   - `fallback_policy`
   - `capability_surface`
12. **公共默认注册表必须提供可 copy-paste 的精确默认 entry**:
   - `config/engines.default.json` 必须至少定义以下默认 entry:
     - `openclaw_native`
     - `gemini_direct_cli`
     - `gemini_acp_reference`
   - 这些 entry 的精确 JSON 内容必须在本 PRD 的 Hardcoded Content 中给出。
13. **正式 enum 只接受 canonical snake_case 值**:
   - 本 issue 明确不提供对历史 hyphenated / mixed legacy 枚举的兼容层。
   - 任何如 `protocol-native`、`returned_handle`、`protocol_native_or_returned_handle` 等历史值都必须被显式拒绝。
14. **`engines.local.json` 的缺失、零字节和损坏必须区别处理**:
   - 文件缺失: 视为合法空覆写,系统必须继续使用 public defaults。
   - 文件存在但为零字节文件: 视为 malformed 配置,必须 fail-closed 并抛出经过脱敏的明确异常。
   - 文件存在且 JSON malformed / 合同不合法: 同样必须 fail-closed 并抛出经过脱敏的明确异常,绝对禁止静默忽略。
15. **Public defaults 也必须受敏感字段禁用规则约束**:
   - `config/engines.default.json` 中若出现 private-sensitive 字段,加载器必须显式拒绝。
16. **系统必须提供正式异常类型 `RegistryValidationError`**,用于区分引擎注册表合同错误与普通通用异常。
17. **若实现拆分到 `scripts/engine_registry.py`**,则 `scripts/config.py` 仍必须对外暴露稳定入口 `load_engine_registry(sdlc_root)`。
18. **`.gitignore` 的保护必须既通过文本规则校验,也通过实际 git ignore 行为校验。**
19. **`openclaw_native` 默认 entry 的 `continuity_mode` 必须明确声明为 `authoritative_resume`**,作为当前系统原生 runtime 的保守已知能力表达。
20. **`RegistryValidationError` 的对外 surfaced error 文本必须以前缀 `[FATAL] Engine Registry validation failed.` 开头。**
21. **未知非敏感字段默认允许存在**,以保留前向兼容性;但任何 private-sensitive 字段出现在 public defaults 中时仍必须被拒绝。
22. **以下字段必须使用明确 enum 约束而不是任意字符串**:
   - `registration_visibility`: `public` | `local_private`
   - `runtime_mode`: `openclaw_native` | `direct_cli` | `acp`
   - `fallback_policy`: `none` | `legacy_direct_cli` | `fail_closed_until_prerequisite_ready`
23. **历史 ADR / 文档若与本 PRD 冲突,一律以本 PRD 为当前实现合同**,不要求 coder 为旧 contract 语义提供兼容层。
24. **private-sensitive 字段在正常加载成功后必须保留在内存 registry object 中供后续 issue 消费**,只在日志、错误、测试输出路径中执行 redaction。
25. **`config/engines.default.json` 只要求进入 repo `config/` 源配置层**,默认由现有发布链路自然带入产物,本 issue 不额外扩 scope 去手工经营 `.dist/` 镜像文件。
26. **`load_engine_registry` 的正式接口必须要求显式传入 `sdlc_root`**,不得隐式默认当前工作目录,以避免配置解析在不同执行环境下出现不确定根路径。
27. **`RegistryValidationError` 必须作为对外统一 surfaced 的配置错误类型**:
   - 对于 JSON parsing error、schema/contract validation error 等内部 cause,允许保留不同底层异常来源;
   - 但对外暴露给调用方、日志和测试断言的主异常类型与主错误文案必须统一到 `RegistryValidationError` 契约之下。
28. **仅来源于 `engines.local.json` 的新增 engine entry 必须固定为 `registration_visibility: local_private`**,不得允许本地新增条目标记为 `public`。
29. **本地 override 不允许把 public default engine 的 `registration_visibility` 从 `public` 改写为 `local_private`**,以保持公共默认 entry 的语义稳定与可预期性。
30. **Redaction 的最低硬要求是 key-based 清洗必做**; pattern-based 清洗可作为补充增强,但本 issue 不要求对未知字段中所有“看起来像路径/endpoint”的值都强制做模式清洗。
31. **现有旧的 runtime contract 参考文件与 ADR 默认保持不动**,不作为本 issue 的清理对象;若其内容与本 PRD 冲突,实现与测试一律以本 PRD 为准。
26. **outer `engines` map 的 key 必须与每个 entry 内部的 `engine_id` 完全一致**;若不一致,必须视为注册表合同错误并抛出 `RegistryValidationError`。
27. **`capability_surface` 当前阶段保持为必填非空字符串字段**,用于表达运行能力面的控制面标签;本 issue 不强制把它进一步收紧为 enum,以保留后续 #52 前的受控扩展空间。
28. **Redaction 的硬性要求至少覆盖最终 surfaced exception text / error message / test-visible output**;若底层 traceback/object 仍保留未清洗私有内容,必须通过异常包装确保外部可见路径不会暴露敏感值。



### 2.2 Non-Functional Requirements
1. **Scope 守卫**: 该实现必须保持薄,不在本 issue 中引入过于复杂的动态插件发现(Plugin Discovery)、复杂的进程生命周期守护(Process Manager)或动态依赖拉取机制。
2. **兼容性前提**: 加载与合并流程必须保持开箱即跑,不依赖 system Python 的非常规库,可继续复用项目既有的 `json` 模块或 `PyYAML`。由于本项目已有 `PyYAML`,注册表文件格式必须采用稳定的 **JSON 格式**（`engines.default.json` 与 `engines.local.json`）,确保轻量、易维护且与现有 `sdlc_config.json` 格式风格高度统一。
3. **Legacy 无感退化**: 当系统缺失本地 `engines.local.json` 且未指定任何私有引擎时,原有 direct CLI Gemini 路径必须能无缝退化工作。

### 2.3 User / Operator Stories
- 作为 `leio-sdlc` 的架构维护者,我希望在配置里以规范的 contract 表达引擎能力,而不是在代码里写一大堆特判,这样才能安全准备后续的 ACP 多引擎路选。
- 作为企业集成商,我希望能在不修改开源仓库核心代码的前提下,通过本地创建一个 `.gitignored` 的 `engines.local.json` 注册并使用我们内部的专有 ACP 引擎。
- 作为对系统安全负责的运维人员,我要求本地覆写配置在解析失败或校验异常时,其具体绝对路径、执行文件名不能被原样打印进日志或系统报错中,防止内部环境特征外溢。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Dual-Layer Configuration File Architecture
在 `config/` 目录下确立以下双层注册表结构:
- **`config/engines.default.json` (必选,入 git)**:
  - 声明公开默认的引擎。至少需要内建表达两类基础默认 entry:
    - Gemini direct CLI
    - OpenClaw-native
    - Gemini ACP (基线审计成果占位，声明其 contract 表现)
- **`config/engines.local.json` (可选,gitignored)**:
  - 供本地覆写或新增私有引擎。
  - 必须将 `config/engines.local.json` 追加进 `.gitignore` 文件。

### 3.2 Registry Loader & Merger Layer
在 `scripts/config.py` (或新增 `scripts/engine_registry.py`, 由 `config.py` 暴露) 中实现 `load_engine_registry(sdlc_root)`:
1. 首先尝试加载 `config/engines.default.json`,获取默认 registry object,其顶层必须包含 `engines` 键。
2. `load_engine_registry` 的正式接口必须要求显式传入 `sdlc_root`,不得隐式依赖当前工作目录。
3. 尝试读取 `config/engines.local.json`,如果文件不存在,则不抛错,直接视为空覆写继续;如果文件存在但为零字节文件或 JSON malformed,则必须抛出经过脱敏的 fatal parsing/validation error。
4. 执行合并逻辑:
   - 本地私有字典的 `engines` 与默认公共字典进行键值合并。
   - 如果本地 `engines` 中包含与默认公共引擎相同的 `engine_id`,则必须以默认 entry 为 base 做字段级 shallow merge,本地字段优先覆盖。
   - 如果是新增的 `engine_id`,则作为一个新的注册条目挂载,且新增条目的 `registration_visibility` 必须固定为 `local_private`。
   - 不允许对同名 `engine_id` 采用整条记录全量替换语义。
   - 不允许本地 override 把 public default engine 的 `registration_visibility` 从 `public` 改写为 `local_private`。
5. 合并完成后,对合并结果中的每一个 `engine` 字典项执行严格的 **Capability Contract Validation**。
6. 若内部实现拆分到 `scripts/engine_registry.py`,则 `scripts/config.py` 仍必须对外暴露稳定入口 `load_engine_registry(sdlc_root)`。


### 3.3 Strict Capability Validation Rules
合并后的每一个注册引擎条目,必须通过以下硬编码校验:
- **最小必填字段** 必须全部存在:
  - `engine_id`
  - `display_name`
  - `runtime_mode`
  - `registration_visibility`
  - `continuity_mode`
  - `handle_acquisition_strategy`
  - `fallback_policy`
  - `capability_surface`
- outer `engines` map 的 key 必须与 entry 内部的 `engine_id` 完全一致;若不一致,必须视为注册表合同错误并被拒绝。
- **`registration_visibility`** 必须严格在授权集合内: `["public", "local_private"]`。
- **`runtime_mode`** 必须严格在授权集合内: `["openclaw_native", "direct_cli", "acp"]`。
- **`continuity_mode`** 必须严格在授权集合内: `["authoritative_resume", "unsupported"]`。
- **`handle_acquisition_strategy`** 必须严格在授权集合内: `["protocol_native", "explicit_returned_handle", "unavailable"]`。
- **`fallback_policy`** 必须严格在授权集合内: `["none", "legacy_direct_cli", "fail_closed_until_prerequisite_ready"]`。
- **`capability_surface`** 在本 issue 中必须是非空字符串,用于表达运行能力面的控制面标签;本 issue 不要求进一步收紧为 enum。
- 本 issue 明确拒绝所有历史 hyphenated 或 mixed legacy 值,包括但不限于:
  - `protocol-native`
  - `returned_handle`
  - `protocol_native_or_returned_handle`
  - `mapped_resume`
  - `heuristic`
- 未知的**非敏感**附加字段默认允许存在,以保留 forward compatibility;但它们不得绕过必填字段和受限 enum 校验。
- 凡不符合上述集合或字段要求的配置条目,必须立即引发一个定制的 `RegistryValidationError`。
- 绝对禁止接受任何如 `mapped_resume`、`heuristic_discovery`、`local_guess` 等非官方收紧语义。
- 若历史 ADR / 文档与上述合同约束冲突,必须以本 PRD 为当前实现合同,不要求实现兼容旧 contract 语义。



### 3.4 Configuration-Level Redaction Discipline
为了物理杜绝私有路径或执行参数随异常外泄,系统必须实现一个异常包装层:
1. 在合并或校验 `engines.local.json` 过程中,任何由于格式错误、合同不合规抛出的异常(例如 ValueError 包含 `executable_path`、`launch_command` 细节时),必须在捕获后进行字符串脱敏。
2. 需要被视为敏感的键至少包括:
   - `executable_path`
   - `launch_arguments`
   - `custom_env_vars`
   - `private_endpoint`
   - `launch_command`
3. 异常和日志流中,凡是检测到上述敏感键对应的值,必须统一被物理替换为 `[REDACTED]`。
4. 在 key-based redaction 之外,允许增加轻量级 pattern-based 补充清洗(例如绝对路径或 endpoint 样式字符串),但本 issue 不要求对未知字段中所有看起来像路径或 endpoint 的值都强制做模式清洗。
5. `config/engines.default.json` 中若出现上述 private-sensitive 字段,加载器也必须显式拒绝,防止 public defaults 泄漏敏感信息。
6. `RegistryValidationError` 必须作为对外统一 surfaced 的配置错误类型;底层可以保留 JSON parsing 或 contract validation 等不同内部 cause,但对外主错误类型与主错误文案必须统一。
7. Redaction 的硬性要求至少必须覆盖最终 surfaced exception text、error message 与 test-visible output;如果底层 traceback/object 内部仍保留私有值,也必须通过异常包装保证外部可见路径不会暴露敏感内容。
8. 尤其在断言或 UAT / test trace 中,确保哪怕配置是错的,输出的 traceback 也是安全不外泄的。


### 3.5 Schema-Driven Architecture Coexistence
本注册表设计仅提供控制面加载与描述接口,它输出一个规范的 registry object 给主程序消费。本 issue 的修改必须遵循“无损嵌入”：
- 注册表加载器本身不调用任何 subprocess。
- 不修改 `agent_driver.py` / `orchestrator.py` 内部的执行分支。
- tests 中使用假配置、内存 mock 字典和假文件测试合并机制,不能破坏现有的测试绿灯。
- `config/engines.default.json` 必须至少提供以下默认公共 entry:
  - `openclaw_native`
  - `gemini_direct_cli`
  - `gemini_acp_reference`
- 其中 `openclaw_native.continuity_mode` 必须明确为 `authoritative_resume`。


## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: 仅有 Public Defaults 时加载正常**
  - **Given** 仓库中存在 `config/engines.default.json` 且配置合规,但缺失 `config/engines.local.json`
  - **When** 调用 `load_engine_registry()`
  - **Then** 系统必须能够成功返回公共默认引擎配置字典,且不抛出任何异常

- **Scenario 2: 本地 Overrides 合并成功且私有引擎生效**
  - **Given** 仓库存在 `config/engines.default.json`,且本地存在合规的 `config/engines.local.json` (声明了一个私有引擎 `private_claw`)
  - **When** 调用 `load_engine_registry()`
  - **Then** 返回的引擎字典中必须成功包含默认引擎与新增的 `private_claw` 引擎,且私有覆写字段已正确合并

- **Scenario 3: 不合规的 ACP 续航语义被硬拦截**
  - **Given** 本地 `config/engines.local.json` 中将一个私有引擎的 `continuity_mode` 声明为 unapproved 语义(如 `"mapped_resume"` 或 `"heuristic"`)
  - **When** 调用 `load_engine_registry()`
  - **Then** 系统必须抛出包含 `RegistryValidationError` 的异常,明确拒绝该配置

- **Scenario 4: 异常 Traceback 中的敏感细节物理脱敏**
  - **Given** 本地 `config/engines.local.json` 包含敏感字段 `executable_path: "/opt/secret_corp/bin/private_adapter"` 且配置因格式错误导致校验失败
  - **When** 配置校验触发并抛出异常
  - **Then** 抛出的最终异常文本、错误输出以及日志中,所有涉及 `"/opt/secret_corp/bin/private_adapter"` 的字符串特征必须被物理替换为 `[REDACTED]`,绝对不准原样输出

- **Scenario 5: 隔离性约束不受破坏**
  - **Given** 重新运行现有的 Gemini ACP validation 或 direct CLI 执行
  - **When** 本注册表模块加载
  - **Then** 缺失私有注册配置不会导致任何既有 public 功能中断,系统行为无感退化

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### 5.1 Core Quality Risk
本 issue 的核心质量风险在于:
1. **合同漏洞**: 允许在配置中登记被 #49 严禁的弱 continuation 语义,导致后续 routing 出现非确定性。
2. **信息泄露**: 错误堆栈、异常输出、断言提示、或 git track 记录里泄漏了本地/私有的 adapter 命令或绝对路径。
3. **越界破坏**: 在编写加载器时,由于过度抽象,改动了主执行驱动(`agent_driver.py`等)的执行代码,破坏了 legacy 路径的稳定性。

### 5.2 Test Strategy
测试必须做到 100% Mock 隔离、100% 行为覆盖。

#### A. File Loader Tests (using `tmp_path`)
- 使用 `tmp_path` 夹具模拟默认 json 和覆写 json。
- 测试:
  - 纯默认加载
  - 默认 + local 合并
  - 重复 `engine_id` 的 shallow merge 覆写
  - 缺失覆写文件
  - 零字节 local 文件触发 redacted fatal error
  - malformed local json 触发 redacted fatal error
- 必须验证 `load_engine_registry()` 返回完整 registry object,而不是裸 engine dict。

#### B. Registry Validation Tests
- 测试不合规 `continuity_mode` 抛 `RegistryValidationError`。
- 测试不合规 `handle_acquisition_strategy` 抛 `RegistryValidationError`。
- 测试缺失必填字段(如 `runtime_mode`、`display_name`)时抛 `RegistryValidationError`。
- 测试历史 hyphenated / mixed legacy 值被显式拒绝。
- 测试 `registration_visibility`、`runtime_mode`、`fallback_policy` 的 enum 约束。
- 测试未知非敏感字段允许通过,但 private-sensitive 字段在 public defaults 中被拒绝。
- 测试 outer map key 与 entry 内 `engine_id` 不一致时被显式拒绝。
- 测试 `capability_surface` 必须为非空字符串。

#### C. Secrecy Redaction Tests
- 特意在 mock config 中塞入带有 `/usr/local/secret_corp/` 或 `/private_bin/` 特征的 `executable_path` 和 `launch_arguments`。
- 制造一个 validation 异常,捕获抛出的错误。
- 最终 surfaced error 文本必须以前缀 `[FATAL] Engine Registry validation failed.` 开头。
- `assert "[REDACTED]"` 存在。
- `assert "secret_corp"` 或 `"private_bin"` 字符在外部可见异常文本和 test-visible 输出中完全被清洗消失。
- 测试 `config/engines.default.json` 若出现 private-sensitive field 时也会被拒绝。

#### D. Git Ignored Enforcement Test
- 自动化测试检查 `.gitignore` 中是否包含 `config/engines.local.json` 规则。
- 同时在临时 git sandbox 中验证该路径真实被 ignore,而不是只检查文本存在。



### 5.3 Quality Goal
- 确保 registry 成为后续 #52 确定性选路的绝对单一事实来源
- 保证本地覆写在任何出错面下的物理安全性
- 所有新增测试在不依赖任何本地/私有环境、网络、API Key 的情况下 100% 通过

## 6. Framework Modifications (框架防篡改声明)
本 PRD 授权修改和新增以下文件:
- `config/engines.default.json` (新增, 随库默认公共配置)
- `scripts/config.py` (修改, 引入注册表加载)
- `scripts/engine_registry.py` (新增, 可选, 承载 registry 解析与校验)
- `tests/test_engine_registry.py` (新增, 承载完整 TDD 校验与安全脱敏测试)
- `.gitignore` (修改, 追加 `config/engines.local.json` 规则)

本 PRD **不授权** 修改以下内容:
- `scripts/agent_driver.py`
- `scripts/orchestrator.py`
- 现有的 `sdlc_config.json` 及其加载契约(允许继承/合并,但不准删除原有字段)
- 任何真实的进程执行分支或 ACP lane 拉起代码
- 将真实的私有 CLI 路径与细节带入 public git 提交

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 结合 #49/#50 的实证成果,确立了配置驱动注册表的设计方向,明确将“配置描述层”与“执行选路层”进行技术解耦。
- **v1.1**: 引入公共默认(`engines.default.json`)与本地覆写(`engines.local.json`)的双层配置隔离架构;钉死严格的合规性校验(Schema Validation),强制执行 #49 确立的二元 ACP continuation 约束;增加了解析层的安全脱敏(Redaction)规范,确保本地敏感绝对路径不随异常外溢。
- **v1.2**: 吸收第一轮 coder-readiness 结果,拍板同名 `engine_id` 覆写必须为 field-level shallow merge,固定 `load_engine_registry()` 返回完整 registry object,补齐 engine entry 的最小必填字段,明确 malformed local config 必须 fail-closed 并 redacted,以及 public defaults 也受私有敏感字段禁用规则约束。
- **v1.3**: 吸收第二轮 coder-readiness 结果,明确零字节 `engines.local.json` 视为 malformed 并 fail-closed,固定 surfaced error 前缀、补充 `registration_visibility` / `runtime_mode` / `fallback_policy` 的 enum 约束,明确未知非敏感字段允许保留前向兼容,并声明历史 ADR 与本 PRD 冲突时以本 PRD 为准。
- **v1.4**: 吸收第三轮 coder-readiness 结果,明确 outer `engines` map key 必须与 `engine_id` 一致,将 `capability_surface` 固定为必填非空字符串,并把 redaction 的硬性要求聚焦到外部可见错误/日志/test-visible 输出路径,避免对内部 traceback 表示施加不必要的实现耦合。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

- **`config_local_filename`**:
```text
config/engines.local.json
```

- **`config_default_filename`**:
```text
config/engines.default.json
```

- **`redacted_placeholder`**:
```text
[REDACTED]
```

- **`validation_error_prefix`**:
```text
[FATAL] Engine Registry validation failed.
```

- **`unsupported_mode_marker`**:
```text
unsupported
```

- **`authoritative_resume_marker`**:
```text
authoritative_resume
```

- **`allowed_strategies_list`**:
```text
protocol_native, explicit_returned_handle, unavailable
```

- **`allowed_registration_visibility_values`**:
```text
public, local_private
```

- **`allowed_runtime_mode_values`**:
```text
openclaw_native, direct_cli, acp
```

- **`allowed_fallback_policy_values`**:
```text
none, legacy_direct_cli, fail_closed_until_prerequisite_ready
```

- **`registry_top_level_key`**:
```text
engines
```

- **`registry_validation_error_name`**:
```text
RegistryValidationError
```

- **`required_default_engine_ids`**:
```text
openclaw_native
gemini_direct_cli
gemini_acp_reference
```

- **`required_engine_entry_fields`**:
```text
engine_id
display_name
runtime_mode
registration_visibility
continuity_mode
handle_acquisition_strategy
fallback_policy
capability_surface
```

- **`default_registry_json_example`**:
```json
{
  "engines": {
    "openclaw_native": {
      "engine_id": "openclaw_native",
      "display_name": "OpenClaw Native",
      "runtime_mode": "openclaw_native",
      "registration_visibility": "public",
      "continuity_mode": "authoritative_resume",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "none",
      "capability_surface": "runtime_managed"
    },
    "gemini_direct_cli": {
      "engine_id": "gemini_direct_cli",
      "display_name": "Gemini Direct CLI",
      "runtime_mode": "direct_cli",
      "registration_visibility": "public",
      "continuity_mode": "unsupported",
      "handle_acquisition_strategy": "unavailable",
      "fallback_policy": "legacy_direct_cli",
      "capability_surface": "engine_managed"
    },
    "gemini_acp_reference": {
      "engine_id": "gemini_acp_reference",
      "display_name": "Gemini ACP Reference",
      "runtime_mode": "acp",
      "registration_visibility": "public",
      "continuity_mode": "authoritative_resume",
      "handle_acquisition_strategy": "protocol_native",
      "fallback_policy": "fail_closed_until_prerequisite_ready",
      "capability_surface": "client_mediated"
    }
  }
}
```

- **`forbidden_legacy_registry_values`**:
```text
protocol-native
returned_handle
protocol_native_or_returned_handle
mapped_resume
heuristic
```

- **`zero_byte_local_config_rule`**:
```text
A zero-byte config/engines.local.json file is malformed and must fail closed with a redacted validation/parsing error.
```

