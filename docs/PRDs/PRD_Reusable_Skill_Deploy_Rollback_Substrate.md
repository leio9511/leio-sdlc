---
Affected_Projects: [leio-sdlc]
Context_Workdir: /home/openclaw/projects/leio-sdlc
---

# PRD: Reusable Skill Deploy Rollback Substrate

## 1. Context & Problem (业务背景与核心痛点)

The `leio-sdlc` repository contains repository-native skills under `skills/`.

Current repository reality:
- `skills/pm-skill/` already has working hard-copy deploy and rollback scripts.
- Additional skills under `skills/<slug>/` should not require bespoke deploy/rollback logic.
- Static dependency analysis shows that `skills/pm-skill/deploy.sh` currently copies `scripts/agent_driver.py` and `scripts/utils_notification.py`, but `pm-skill` itself does not directly consume those files as part of its own runtime logic.
- Static dependency analysis also shows that staged runtime provisioning / smoke-before-swap is part of the root `leio-sdlc` deploy contract in `deploy.sh`, not part of the current `skills/pm-skill/deploy.sh` behavior.

The problem is that deploy and rollback behavior should not be redesigned, re-audited, and re-discussed for every repository skill.

The existing `pm-skill` deploy/rollback behavior should be generalized into a reusable substrate for repository skills, but only for the behavior that is actually part of the `pm-skill` skill-level deploy contract. Historical baggage that is not a proven `pm-skill` runtime dependency should not be promoted into the shared substrate by default.

## 2. Requirements & User Stories (需求定义)

### 2.1 Primary goal

Create a reusable deploy/rollback mechanism for skills under:

```text
skills/<slug>/
```

The mechanism must preserve the existing `pm-skill` behavior while making it reusable by other repository skills.

### 2.2 Functional requirements

- Provide generic entrypoints with positional slug syntax:

```text
scripts/skill_deploy.sh <slug> [--no-restart]
scripts/skill_rollback.sh <slug> [--no-restart]
```

- The deploy entrypoint must deploy `skills/<slug>/` to the resolved runtime skills directory.
- The rollback entrypoint must restore the latest backup for that runtime skill.
- Preserve existing `pm-skill` deploy behavior unless explicitly changed by this PRD.
- Preserve existing `pm-skill` rollback behavior unless explicitly changed by this PRD.
- Remove `pm-skill` deploy behaviors that are not proven runtime dependencies of `pm-skill` itself, specifically the repository-root helper-file copy, unless later evidence demonstrates they are required.
- Convert `skills/pm-skill/deploy.sh` and `skills/pm-skill/rollback.sh` into thin compatibility wrappers around the generic mechanism, or otherwise make them delegate to the generic mechanism while keeping their existing command interface.
- Support `HOME_MOCK` so deploy/rollback tests can run without touching the real user runtime home.
- Support `SDLC_RUNTIME_DIR` for non-mock runtime skill directory override, matching existing behavior.
- Preserve backup storage under:

```text
$HOME/.openclaw/.releases/<slug>/backup_*.tar.gz
```

with `HOME_MOCK` applied when present.

- Preserve production runtime placement under:

```text
$HOME/.openclaw/skills/<slug>
```

or `${SDLC_RUNTIME_DIR}/<slug>` when `SDLC_RUNTIME_DIR` is set outside mock mode.

- Preserve the existing hard-copy deployment style: stage into a temp directory, back up the previous runtime directory when present, then swap the staged directory into production.
- Preserve rollback from the latest backup tarball.
- Preserve cleanup of older backups using the existing retention policy unless a safer equivalent is needed.
- Preserve Gemini CLI link behavior for deployed skills when `gemini` is available, if this remains part of the current `pm-skill` deploy contract.
- Treat Gemini best-effort link as a deploy-time post-step only; rollback is not required to re-run Gemini link behavior.

### 2.3 Non-goals

This PRD does not authorize:
- changing skill text content as part of the deploy/rollback refactor
- adding semantic tests for skill prose
- inventing custom deploy/rollback flows for individual skills
- changing global skill-discovery semantics outside this repository's deploy/rollback support
- changing orchestrator/coder/reviewer/auditor pipeline behavior
- changing PM/Auditor governance rules

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 Reuse the pm-skill deployment baseline

The existing `skills/pm-skill/deploy.sh` and `skills/pm-skill/rollback.sh` are the behavioral baseline.

The implementation should extract or centralize the slug-independent parts of those scripts into shared repository-level scripts or a shared shell library.

Acceptable designs include either:

1. shared executable scripts such as:

```text
scripts/skill_deploy.sh
scripts/skill_rollback.sh
```

or

2. a shared library plus small executable entrypoints, such as:

```text
scripts/skill_deploy_lib.sh
scripts/skill_deploy.sh
scripts/skill_rollback.sh
```

The final design should prefer simple shell code over a new Python runtime dependency unless the repository already has a clearly better existing helper.

### 3.2 Slug-driven behavior

The generic mechanism must derive source, production, release, temp, and old paths from the supplied slug.

For slug `<slug>`:

```text
source:   <repo_root>/skills/<slug>/
prod:     <resolved_skills_dir>/<slug>
releases: <resolved_openclaw_home>/.releases/<slug>/
tmp:      <resolved_skills_dir>/.tmp_<slug>
old:      <resolved_skills_dir>/.old_<slug>
```

The generic deploy should fail fast if:
- the slug is empty
- `skills/<slug>/` does not exist
- `skills/<slug>/SKILL.md` does not exist
- the slug contains path traversal or path separators

### 3.3 Keep skill-local wrappers for compatibility

`skills/pm-skill/deploy.sh` and `skills/pm-skill/rollback.sh` must remain callable.

They should delegate to the generic mechanism with slug `pm-skill`.

Repository skills may keep skill-local deploy/rollback wrappers when that improves operator ergonomics, but those wrappers must delegate to the generic mechanism and must not duplicate deployment logic.

Any repository skill intended to participate in `kit-deploy.sh` must provide a skill-local `deploy.sh` thin wrapper that delegates to `scripts/skill_deploy.sh <slug>`.

`kit-deploy.sh` discovers deployable repository skills by executing `skills/*/deploy.sh`; it does not directly deploy every `skills/<slug>/` directory automatically.

Skill-local `rollback.sh` wrappers are optional but recommended when operators need a familiar per-skill rollback command. They must delegate to `scripts/skill_rollback.sh <slug>` and must not duplicate rollback logic.

### 3.4 Scope boundary: shared skill substrate vs non-skill root deploy contract

The generic skill deploy/rollback substrate should cover behavior that is genuinely part of skill-local deployment for repository skills under `skills/<slug>/`.

Static analysis performed before this PRD revision establishes:
- `skills/pm-skill/deploy.sh` currently performs slug-local hard-copy deployment, backup, atomic promotion, and Gemini best-effort linking.
- `skills/pm-skill/deploy.sh` currently copies `scripts/agent_driver.py` and `scripts/utils_notification.py`, but the `pm-skill` source tree itself does not directly consume those files in its own runtime logic.
- staged runtime provisioning / smoke-before-swap is part of the root `deploy.sh` contract for the `leio-sdlc` runtime package, not part of the current `skills/pm-skill/deploy.sh` path.

Therefore this PRD must treat the following as in scope for the shared skill substrate:
- slug validation
- source directory validation
- resolved runtime skill directory placement
- temp staging
- backup creation
- atomic swap / promotion
- rollback from latest backup
- backup retention
- common default excludes
- optional skill-local `.release_ignore`
- thin wrapper delegation and `kit-deploy.sh` participation semantics
- Gemini best-effort link behavior if preserved as a shared post-deploy step

This PRD must treat the following as out of scope for the shared skill substrate unless later evidence proves they are true skill-level dependencies:
- repository-root helper-file bundling for `pm-skill`
- root `leio-sdlc` staged runtime provisioning / smoke-before-swap
- root-runtime `.venv` provisioning logic
- root-runtime smoke contract

### 3.5 Packaging ignore policy

The generic deploy mechanism should provide common default excludes for repository skills, including at least:

```text
.git
__pycache__
dist
.pytest_cache
.mypy_cache
.ruff_cache
```

Skill-local `.release_ignore` files are optional. A skill-specific `.release_ignore` may extend the common packaging excludes with additional skill-local exclusions only; it does not re-include artifacts already excluded by the shared default policy.

This PRD does not require every skill to define its own `.gitignore` or `.release_ignore`.

### 3.6 Validation philosophy

Validation should focus on deploy/rollback behavior, not skill text semantics.

It is acceptable to test:
- source directory validation
- runtime directory creation
- backup creation
- rollback restore
- wrapper delegation
- `HOME_MOCK` isolation
- `SDLC_RUNTIME_DIR` resolution

It is not acceptable to add tests asserting skill prose semantics.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1: generic deploy installs a repository skill**
  - **Given** a repository skill exists at `skills/<slug>/SKILL.md`
  - **And** `HOME_MOCK` points to an empty temporary home
  - **When** the generic deploy mechanism is invoked for that slug
  - **Then** the deployed runtime directory exists at `$HOME_MOCK/.openclaw/skills/<slug>`
  - **And** the deployed directory contains `SKILL.md`

- **Scenario 2: generic deploy creates a backup of an existing runtime skill**
  - **Given** a runtime directory already exists for a skill slug
  - **And** the corresponding repository source skill exists
  - **When** generic deploy is invoked for that slug
  - **Then** the previous runtime directory is archived under `$HOME_MOCK/.openclaw/.releases/<slug>/backup_*.tar.gz`
  - **And** the runtime directory is replaced by the new deployed copy

- **Scenario 3: generic rollback restores the latest backup**
  - **Given** a backup tarball exists under `$HOME_MOCK/.openclaw/.releases/<slug>/`
  - **And** the current runtime directory differs from that backup
  - **When** generic rollback is invoked for that slug
  - **Then** the runtime directory is restored from the latest backup

- **Scenario 4: pm-skill deploy wrapper remains compatible**
  - **Given** `skills/pm-skill/deploy.sh` exists
  - **And** `HOME_MOCK` points to a temporary home
  - **When** `skills/pm-skill/deploy.sh` is run with existing supported flags such as `--no-restart`
  - **Then** it deploys `pm-skill` through the generic mechanism
  - **And** the observable runtime output remains compatible with the previous hard-copy deploy behavior

- **Scenario 5: pm-skill rollback wrapper remains compatible**
  - **Given** `skills/pm-skill/rollback.sh` exists
  - **And** a valid pm-skill backup exists in the mocked releases directory
  - **When** `skills/pm-skill/rollback.sh` is run with existing supported flags such as `--no-restart`
  - **Then** it rolls back `pm-skill` through the generic mechanism

- **Scenario 6: skill-local wrappers do not duplicate deploy logic**
  - **Given** a repository skill provides skill-local deploy or rollback wrappers
  - **When** those wrappers are inspected or executed
  - **Then** they must delegate to the generic mechanism
  - **And** they must not duplicate the hard-copy deploy/rollback implementation

- **Scenario 6b: kit-deploy deploys wrapper-enabled repository skills**
  - **Given** a repository skill provides `skills/<slug>/deploy.sh`
  - **When** `kit-deploy.sh` is executed
  - **Then** that skill-local deploy wrapper is invoked
  - **And** the wrapper deploys the skill through the generic deploy mechanism
  - **And** repository skill directories without `deploy.sh` are not implicitly deployed by `kit-deploy.sh`

- **Scenario 7: invalid slugs fail safely**
  - **Given** a caller passes an empty slug, a slug containing `/`, or a slug containing `..`
  - **When** generic deploy or rollback is invoked
  - **Then** it fails without modifying runtime skill directories

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)

### Core quality risks

- Breaking existing `pm-skill` deploy/rollback behavior while extracting shared logic
- Accidentally retaining historical `pm-skill` deploy baggage that is not a real skill runtime dependency
- Incorrectly pulling root `leio-sdlc` runtime provisioning/smoke behavior into the shared skill substrate
- Touching the real runtime home during tests
- Failing to restore from backup during rollback
- Accidentally creating one-off per-skill deployment logic instead of a reusable substrate

### Verification approach

Use sandboxed shell/integration tests with `HOME_MOCK` and temporary directories.

Tests should exercise the generic deploy/rollback entrypoints and the existing `pm-skill` wrappers.

Mock or isolate:
- `$HOME` / `HOME_MOCK`
- runtime skill directory
- release backup directory
- optional external tools such as `gemini` if behavior must be observed

Do not perform live deployment to the real runtime directory as part of automated tests.

Do not add tests that assert the exact natural-language content of skill files.

## 6. Framework Modifications (框架防篡改声明)

Authorized modifications:
- `scripts/skill_deploy.sh`
- `scripts/skill_rollback.sh`
- optional shared shell library under `scripts/` if needed
- `skills/pm-skill/deploy.sh`
- `skills/pm-skill/rollback.sh`
- optional skill-local deploy/rollback wrappers under `skills/<slug>/`
- tests covering generic deploy/rollback behavior and wrapper compatibility
- cleanup or removal of `pm-skill` helper-file bundling if implementation evidence confirms it is not a true runtime dependency

Not authorized:
- changes to skill prose unrelated to deploy/rollback mechanics
- text-semantic tests for skill documentation
- changes to orchestrator/coder/reviewer/auditor core pipeline behavior
- changes to global skill discovery semantics outside this repository's deploy/rollback support

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)

> **CRITICAL INSTRUCTION FOR PLANNER & CODER**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial PRD focused on generalizing the existing `pm-skill` hard-copy deploy/rollback behavior for all repository skills under `skills/<slug>/`.
- **v1.1**: Static dependency analysis established that repository-root helper-file copy is not currently proven to be a true `pm-skill` runtime dependency, and that staged runtime provisioning / smoke-before-swap belongs to the root `leio-sdlc` deploy contract rather than the `pm-skill` skill-local deploy path. The PRD scope was narrowed accordingly.

---

## 7. Hardcoded Content (硬编码内容)

None.
