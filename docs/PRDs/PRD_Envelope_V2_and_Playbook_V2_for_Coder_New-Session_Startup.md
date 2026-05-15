---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Envelope V2 and Playbook V2 for Coder New-Session Startup

## 1. Context & Problem (业务背景与核心痛点)

`leio-sdlc` 现有 coder 启动路径已经从早期“大块 inline prompt + prompts.json 模板”逐步迁移到 `envelope_assembler.py` 驱动的结构化 envelope 架构。这次迁移解决了一个真实问题：当 PRD、本地上下文、协议说明与角色规则都被一次性 inline 成很长的启动 prompt 时，模型经常会失焦，进而跳过最基础的动作（如不输出要求产物、没有真正执行代码修改、或把启动回合耗在总结和确认上）。

但现有 envelope 架构又引入了另一类问题：角色 playbook 被从“startup authority”降级为 `REFERENCE INDEX` 中的被引用材料。也就是说，coder 要先 obey 一次 envelope 去读 playbook，再 obey 第二次 playbook 本身，playbook 不再是启动时的一阶约束，而变成二阶引用文档。

实际观察中，这种弱化在 coder 身上最明显：
- 尤其在 GPT/GPTX 系列模型上，coder 第一轮更容易出现“不干活 / 只 acknowledge / 只总结计划”的行为；
- DS4P / Gemini 类模型表现相对更稳定；
- 这说明 coder 启动权威很可能对模型族敏感，而不仅仅是任务复杂度问题。

我们已经在设计讨论中确认：
1. 现有 `coder_playbook.md` 可以收缩成更短、更硬的 SDLC operating contract；
2. 一旦 playbook 已经被收缩为启动控制面板（launch control panel），再把它只作为 reference 提供，就会再次削弱其权威；
3. same-session continuation prompt 与 new-session startup prompt 是两类不同问题，本 PRD 不应把它们混在一起治理。

因此，本 PRD 的目标不是直接重写现有 v1 流程，而是**新增一套 coder-only 的 Playbook V2 + Envelope V2，用于 new-session startup 的手动双版本切换与对照**，在不影响现有稳定流程的前提下，支持：
- 让精简后的 coder playbook 直接 inline，并观察是否改善 first-turn execution；
- 把 envelope 收缩成“仅负责三个 new-session 启动壳”的薄层，避免重新引入 giant prompt 失焦问题；
- 在测试结果不佳时，通过手动改回 v1 配置完成快速回退。

本 PRD 明确只覆盖 coder 的 new-session 启动三场景：
- `initial`
- `revision_bootstrap`
- `system_alert_bootstrap`

本 PRD **不**处理：
- same-session revision / system_alert JIT prompt 重构；
- reviewer / verifier / auditor / planner 的 envelope/playbook v2；
- 全局 prompt taxonomy 统一重写。

## 2. Requirements & User Stories (需求定义)

### Scope Framing

#### Primary Objective
为 coder 新增一套并存的 `playbook_v2` + `envelope_v2` 启动路径，专门用于 new-session startup，并保持 v1 完整不动，以支持手动双版本切换与对照。

#### Secondary Objective
通过更强的一阶 startup authority，降低 coder 在新 session 首轮出现“只 acknowledge / 不执行 / 不闭环”的概率，特别是在 GPT/GPTX 系列模型上。

#### Scope Boundary
- 本 PRD 不替换现有 `coder_playbook.md`。
- 本 PRD 不原地修改现有 envelope v1 的行为契约。
- 本 PRD 不治理 same-session JIT continuation prompt。
- 本 PRD 不把其他角色一并迁移到 v2。

### Functional Requirements

#### R1. Preserve v1, add v2 side-by-side
- 系统必须保留现有 coder playbook / envelope v1 的文件与可调用路径，不得删除或破坏其回退能力。
- 系统必须新增并行的 `playbook_v2` 与 `envelope_v2` 路径，而不是覆盖 v1。
- 版本选择机制必须通过单一明确的配置入口控制：`config/sdlc_config.json` 中新增 `coder_playbook_version`。
- `coder_playbook_version` 的合法值必须至少包含 `1` 与 `2`。
- `coder_playbook_version` 默认值必须为 `2`。
- 当 `coder_playbook_version=1` 时，coder new-session startup 必须回到现有 v1 行为。
- 当 `coder_playbook_version=2` 时，coder new-session startup 必须使用本 PRD 定义的 v2 路径。
- same-session continuation 不得读取或受该开关影响。
- 若 v2 实验效果不佳，必须能够仅通过把 `coder_playbook_version` 从 `2` 改回 `1` 完成无损回退。

#### R2. Restrict v2 to coder new-session startup only
- v2 首期只覆盖 coder 的以下三种 new-session 启动场景：
  - `initial`
  - `revision_bootstrap`
  - `system_alert_bootstrap`
- same-session `revision` 和 `system_alert` 继续沿用现有 JIT continuation 机制，不得因为本 PRD 被迫改成完整 envelope。

#### R3. Inline Playbook V2 as startup authority
- `coder_playbook_v2` 必须以 inline 内容方式直接进入 new-session startup prompt，而不是只通过 reference path 提供。
- 这份 inline playbook 必须承担三类通用职责：
  1. coder 执行 posture；
  2. SDLC hard constraints；
  3. completion / git hygiene / file operation contract。
- v2 prompt 不得再次把这份简化后的 playbook 降级回“read it later”的二阶引用。

#### R4. Keep Envelope V2 as a thin scenario shell
- `envelope_v2` 的职责必须被限制为：
  - 定义当前是哪个 new-session 启动场景；
  - 注入该场景特有的 mission；
  - 注入该场景特有的 inline action target（如 reviewer feedback / system alert）；
  - 注入该场景的 required refs、workdir、以及 continuation semantics。
- `envelope_v2` 不得重新膨胀成大而全的 mixed-purpose behavior manual。

#### R5. Coder Playbook V2 content contract
`coder_playbook_v2` 必须至少明确包含以下内容：
- 执行而非 acknowledge 的角色定位；
- required refs must be read before coding；
- PR contract 是 immediate execution target；
- PRD 是 authoritative product requirement source；
- coder 负责自主探索当前实现和正确文件路径；
- 使用 Red → Green → Refactor 工作法；
- relevant tests + `./preflight.sh`（若存在）必须跑绿；
- 跟随现有项目架构风格与约定；
- 优先最简单、最贴合当前代码库的实现；
- 不引入没有明确收益的抽象 / design pattern；
- 不切 branch、不 push、不 merge；
- 禁止 `git add .`；
- 必须通过 `python3 scripts/runtime_git_identity.py --role coder -- commit -m "feat/fix: <description>"` 提交；
- completion contract：green + reviewable + clean + committed + report hash；
- continuation rules：revision 是 execution work、system alert 需修到 healthy、existing branch/on-disk state 在 continuation 中是 authoritative；
- file operation policy：优先 `read` / `write` / `edit`。

#### R6. Scenario-specific reference / inline contract
对于 v2 三个场景，prompt 结构必须符合以下权责分离：

##### R6.1 Initial
- 必须 inline：
  - 场景 mission；
  - inline `coder_playbook_v2`。
- 必须作为 refs 提供：
  - PR contract；
  - PRD。
- 不得 inline reviewer feedback 或 system alert。

##### R6.2 Revision bootstrap
- 必须 inline：
  - 场景 mission；
  - inline `coder_playbook_v2`；
  - reviewer feedback。
- 必须作为 refs 提供：
  - PR contract；
  - PRD。
- 必须明确：
  - 这不是 fresh start；
  - existing branch state / on-disk implementation 是 authoritative；
  - reviewer feedback 是 immediate action target。

##### R6.3 System alert bootstrap
- 必须 inline：
  - 场景 mission；
  - inline `coder_playbook_v2`；
  - system alert。
- 必须作为 refs 提供：
  - PR contract；
  - PRD。
- 必须明确：
  - 这不是 fresh start；
  - existing branch state / on-disk implementation 是 authoritative；
  - system alert 是 immediate corrective target。

#### R7. Versioned artifacts and observability
- v2 启动路径必须产生清晰的调试产物，至少能够分辨：
  - 使用的是 v1 还是 v2；
  - 场景类型（initial / revision_bootstrap / system_alert_bootstrap）；
  - 渲染后的最终 prompt。
- 这类产物必须足以支持后续比较 GPT/GPTX 与 DS4P/Gemini 在 v1/v2 下的行为差异。

### Non-Goals
- 不对 same-session revision/system_alert continuation prompt 做结构性重写。
- 不对 planner / reviewer / verifier / auditor 的 playbook/envelope 进行本次 v2 实验。
- 不引入新的全局 prompt 引擎、事件总线、或统一 skill registry 重构。
- 不要求本次解决所有 coder 质量问题；本 PRD 只聚焦 new-session startup authority。

### User Stories
- 作为 manager，我希望在不破坏现有稳定路径的前提下保留 coder 新启动协议的两个版本，这样我可以通过改 config 手动切换 v1/v2 并在不同场景下做对照。
- 作为 manager，我希望 GPT/GPTX 在 coder 首轮更稳定地进入真实执行，而不是只确认任务或总结计划。
- 作为维护者，我希望 playbook_v2 与 envelope_v2 的职责边界清晰，这样不会再次做出一个既长又混乱的 giant prompt。
- 作为调试者，我希望能明确知道一次 coder 启动到底用了 v1 还是 v2，以及渲染后的最终 prompt 长什么样，这样模型行为差异可复盘。

## 3. Architecture & Technical Strategy (架构设计与技术路线)

本 PRD 采用“并存 v2、薄壳 envelope、inline playbook authority、单一组装真源”的策略，而不是原地修改现有 v1。

### Decision A — Keep v1 untouched; add explicit v2 parallel path
- 保留现有 `coder_playbook.md` 与现有 coder new-session v1 渲染路径不变，确保随时可回退。
- 新增独立文件 `playbooks/coder_playbook_v2.md`。
- `scripts/envelope_assembler.py` 必须作为 coder new-session v2 prompt 的唯一组装真源（single assembly authority），统一负责以下三类场景的 v2 prompt 渲染：
  - `initial`
  - `revision_bootstrap`
  - `system_alert_bootstrap`
- `scripts/spawn_coder.py` 只负责识别场景、读取配置、并把场景参数传入 `scripts/envelope_assembler.py`；不得在 `spawn_coder.py` 中再手写第二套 v2 prompt 组装逻辑。
- `scripts/spawn_coder.py` 负责读取 `config/sdlc_config.json` 中的 `coder_playbook_version`，并且只在上述三类 new-session 场景路由时使用该值。
- same-session continuation 路径不得读取该值，也不得因为该值被升级为 full envelope。
- `coder_playbook_version` 默认值必须为 `2`，并允许通过显式改成 `1` 手动切回 v1。
- 本开关的目的仅是手动版本切换与人工对照，不承担 rollout、override、灰度分流或按比例试验职责。


### Decision B — Playbook V2 becomes inline authority, not ref-first material
- v2 设计下，简化后的 coder playbook 不再主要作为 ref 生效。
- 它必须作为 prompt 正文中的 `## CODER PLAYBOOK`（或等价高权重段）直接 inline。
- 只有在需要 source-of-truth traceability 时，才允许保留其文件路径作为附加调试/追溯信息；不得把其有效性再次依赖于“先读 reference”。

### Decision C — Envelope V2 is scenario shell, not a second playbook
- envelope v2 只负责场景化启动信息，不应重新承载完整通用 coder 规则。
- 任何通用 coder 规则应优先写进 `playbook_v2`，而不是在 envelope v2 与 playbook v2 之间重复。
- 这意味着 envelope v2 应明确避免重新写一遍完整的 git hygiene / TDD / completion prose。

### Decision D — Use scenario-specific mission and action-target ordering
三个场景必须有不同的启动顺序与 authority order：

#### Initial ordering
1. role
2. mission（fresh execution start）
3. inline playbook_v2
4. refs（PR contract / PRD）
5. 当前 run 约束（如 locked workdir）
6. start

#### Revision bootstrap ordering
1. role
2. mission（recovery bootstrap, not fresh start）
3. inline playbook_v2
4. refs（PR contract / PRD）
5. inline reviewer feedback
6. continuation-specific constraints
7. start

#### System alert bootstrap ordering
1. role
2. mission（recovery bootstrap, not fresh start）
3. inline playbook_v2
4. refs（PR contract / PRD）
5. inline system alert
6. continuation-specific constraints
7. start

该排序的目的不是美观，而是让模型一眼识别：
- 当前是否是新开题；
- immediate action target 是什么；
- 通用 coder contract 是什么。

### Decision E — Keep references minimal and role-appropriate
对于 coder new-session v2：
- refs 应只保留需要被“阅读/重读”的任务材料：PR contract、PRD；
- reviewer feedback / system alert 必须 inline，而不是只做 ref；
- playbook_v2 已 inline 后，不应再把其主要生效路径放回 reference。
- scenario shell 只允许承载场景特有启动信息，不得在 shell 中重复完整的 git hygiene、TDD、completion、file-operation 通用规则集合。
- prompt 组装真源必须唯一：任何 v2 new-session prompt 的正文结构都只能由 `scripts/envelope_assembler.py` 生成，`scripts/spawn_coder.py` 不得维护平行的第二套 v2 prompt 文案。

### Decision F — Slim playbook, not giant prompt reconstruction
`playbook_v2` 应体现以下取舍：
- 保留 SDLC-specific hard constraints；
- 保留 concise 的 Red → Green → Refactor 工作法；
- 保留“遵循现有架构风格、偏向最简单合适实现、避免无谓 abstraction/pattern”的质量导向；
- 删除或下沉 prompt-protocol 教学、大段 envelope taxonomy 解释、以及通用编程教材式 prose。

### Target Files / Modules
本 PRD 允许并预期在最小必要范围内修改以下模块：
- `playbooks/coder_playbook_v2.md`
- `scripts/spawn_coder.py`
- `scripts/envelope_assembler.py`
- `config/sdlc_config.json`
- 与 coder prompt/render/debug artifact 相关的测试

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: v1 coder startup remains available when `coder_playbook_version=1`**
  - **Given** the existing coder startup flow and `coder_playbook_version=1`
  - **When** coder enters a new-session startup path
  - **Then** the system uses the v1 playbook/envelope behavior for that new-session launch
  - **And** no v2-only prompt structure is injected by accident

- **Scenario 2: initial new-session startup uses v2 when `coder_playbook_version=2`**
  - **Given** a coder initial new-session launch and `coder_playbook_version=2`
  - **When** the startup prompt is rendered
  - **Then** the prompt contains an inline coder playbook v2 block
  - **And** the prompt contains PR contract and PRD references
  - **And** the prompt does not require coder to first read playbook_v2 from a reference path in order to receive its operating rules

- **Scenario 3: revision bootstrap v2 inlines reviewer feedback as the immediate target**
  - **Given** a coder revision bootstrap launch with v2 selected
  - **When** the startup prompt is rendered
  - **Then** reviewer feedback appears inline in the prompt
  - **And** the prompt explicitly states that this is not a fresh task start
  - **And** the prompt explicitly states that the current branch state / on-disk implementation is authoritative

- **Scenario 4: system alert bootstrap v2 inlines the alert as the immediate target**
  - **Given** a coder system alert bootstrap launch with v2 selected
  - **When** the startup prompt is rendered
  - **Then** the system alert appears inline in the prompt
  - **And** the prompt explicitly states that this is not a fresh task start
  - **And** the prompt explicitly states that the current branch state / on-disk implementation is authoritative

- **Scenario 5: v2 playbook includes explicit Red → Green → Refactor guidance**
  - **Given** coder playbook v2
  - **When** the playbook content is rendered inline into any new-session v2 prompt
  - **Then** it explicitly instructs the coder to use a Red → Green → Refactor workflow
  - **And** it explicitly allows/encourages refactor when needed to keep quality high

- **Scenario 6: v2 playbook keeps SDLC-hard git and completion contracts explicit**
  - **Given** coder playbook v2
  - **When** it is rendered into a new-session v2 prompt
  - **Then** it explicitly forbids branch switching, push, merge, and `git add .`
  - **And** it explicitly includes the runtime commit helper contract
  - **And** it explicitly defines completion as green + reviewable + clean + committed + hash reported

- **Scenario 7: v2 prompt keeps the scenario shell thin and avoids duplicate full-rule restatement**
  - **Given** a v2 new-session coder prompt
  - **When** the prompt is rendered
  - **Then** common coder operating rules appear in the inline playbook block
  - **And** the scenario shell outside that block is limited to scenario-specific startup information only:
    - role
    - mission
    - refs
    - inline reviewer feedback or inline system alert when applicable
    - locked workdir / continuation-specific constraints
    - start instruction
  - **And** the scenario shell does not restate the full git hygiene, TDD, completion, and file-operation rule set a second time outside the inline playbook block

- **Scenario 8: same-session revision and system-alert flows remain on the existing JIT continuation path**
  - **Given** a same-session revision or same-session system alert coder continuation
  - **When** the flow executes
  - **Then** it does not get forcibly upgraded into a full v2 new-session envelope
  - **And** existing same-session continuation semantics remain intact

- **Scenario 9: v2 selection is observable in debug artifacts**
  - **Given** a coder new-session launch using v2
  - **When** debug artifacts are written
  - **Then** the artifacts clearly identify the startup as v2
  - **And** they preserve the rendered prompt used for that launch
  - **And** they expose enough identity to distinguish the selected startup version, scenario type, and assembly path source

- **Scenario 10: manual config switching can return new-session coder startup to v1**
  - **Given** the project decides that v2 is not performing well enough
  - **When** `coder_playbook_version` is changed from `2` to `1` in `config/sdlc_config.json`
  - **Then** subsequent coder new-session launches return to the prior v1 behavior
  - **And** this switch does not require redesigning same-session continuation flows

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core quality risk
本 PRD 的核心风险不是“代码能不能跑”，而是 **prompt authority 架构改动是否会在改善首轮执行率的同时重新引入 prompt 失焦**。

我们要同时防两种退化：
1. v1 弱 authority 问题：coder 首轮只 acknowledge / 不执行；
2. 旧式 giant prompt 问题：prompt 太肥，模型抓不住当前任务重心。

### Test approach
应采用“结构验证 + 路由验证 + targeted behavioral contract verification”的策略。

#### A. Prompt structure / rendering tests
重点验证：
- v2 三个场景的 prompt 是否包含预期 section；
- inline playbook_v2 是否真的被内嵌；
- reviewer feedback / system alert 是否在正确场景下被 inline；
- refs 是否只保留 PR contract / PRD；
- v1 与 v2 的选择逻辑是否清晰。

#### B. Routing / version selection tests
重点验证：
- `coder_playbook_version=1` 时，new-session coder 启动仍走原有 v1；
- `coder_playbook_version=2` 时，new-session `initial` / `revision_bootstrap` / `system_alert_bootstrap` 正确切到 v2；
- same-session continuation 不读取 `coder_playbook_version`，也不误入 v2 full envelope；
- 仅通过修改 `config/sdlc_config.json` 中的 `coder_playbook_version`，即可在 v1/v2 之间切换 new-session coder 启动行为；
- v2 prompt 组装只存在单一来源：`scripts/envelope_assembler.py`，不得由 `spawn_coder.py` 平行维护第二套 v2 prompt 正文。

#### C. Artifact/debug visibility tests
重点验证：
- debug artifacts 能显示 v1/v2 和场景类型；
- rendered prompt 可追溯。

### Mocking guidance
- 单元/组装测试应以 mocked prompt assembly and routing 为主。
- 不要求在本 PRD 范围内直接用 live LLM 行为作为唯一 correctness gate。
- 若后续要评估 GPT/GPTX 与 DS4P/Gemini 的实际执行差异，可在本 PRD 完成后补充独立 experiment / smoke workflow，但不应把 live-model variance 作为本次实现唯一验收方式。

### Quality goal
- v2 必须首先证明自己在结构与路由层面是正确、可切换、可回滚的；
- 然后才有资格进入更高层的真实模型行为对照实验。

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_coder.py`
- `scripts/envelope_assembler.py`
- `playbooks/coder_playbook_v2.md`
- `config/sdlc_config.json`（新增 `coder_playbook_version` 键）
- 必要的 coder prompt/render/debug artifact 测试文件

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]** 
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: 初版将问题定义为“当前 envelope 把 playbook 降级为 reference，导致 coder new-session startup authority 不足，尤其在 GPT/GPTX 上更容易出现首轮不执行”。
- **v1.1 Scope Narrowing**: 明确本 PRD 不治理 same-session continuation，也不一次迁移其他角色；只做 coder new-session v2。
- **v1.2 Design Decision**: 放弃“把 playbook 精简后再重新 reference 化”的方案；改为“精简后的 playbook_v2 直接 inline，envelope_v2 只做三场景启动壳”。
- **v1.3 Safety Decision**: 明确 v1 保持不动，v2 并存，支持手动双版本切换与快速回退，而不是 rollout/override 机制。
- **v1.4 Auditor Correction**: 补充 `coder_playbook_version` 的精确定义、单一 prompt assembly 真源，以及需要写死到 Section 7 的版本/标识文本。

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL INSTRUCTION FOR PM & CODER]**
> **Anti-Hallucination Policy (防幻觉策略):** 大语言模型极易在生成提示词、错误信息、日志文案或配置文件时进行自由发挥（幻觉）。
> 凡是本需求涉及需要精确输出的字符串（如 Error Message、正则法则、配置文件等），**PM 必须在此处使用 Markdown 代码块（单行或多行）一字不落地定义清楚**。
> **Coder 必须且只能从本章节进行 Copy-Paste（复制粘贴），绝对禁止对以下内容进行任何改写或二次加工。**
> 如果本需求不涉及任何写死的文本，请明确填写 "None"。

### Exact Text Replacements:

- **`coder_playbook_version_config_key`**:
```text
coder_playbook_version
```

- **`coder_playbook_version_v1_value`**:
```text
1
```

- **`coder_playbook_version_v2_value`**:
```text
2
```

- **`coder_playbook_v2_filename`**:
```text
playbooks/coder_playbook_v2.md
```

- **`coder_v2_assembly_authority_path`**:
```text
scripts/envelope_assembler.py
```

- **`coder_completion_report_template`**:
```text
Tests green, ready for review. Latest commit hash is <HASH>.
```

- **`runtime_commit_helper_template`**:
```text
python3 scripts/runtime_git_identity.py --role coder -- commit -m "feat/fix: <description>"
```
