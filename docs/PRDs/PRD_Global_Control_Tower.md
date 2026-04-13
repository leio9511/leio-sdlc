---
Affected_Projects: [leio-sdlc]
---

# PRD: Global_Control_Tower

## 1. Context & Problem (业务背景与核心痛点)
The "Agentic Company" operates across multiple projects (leio-sdlc, AMS, ClawOS) simultaneously. When an agent or human operator starts a new session, there is no single source of truth to quickly understand the current state of all projects. Critical state information is scattered across Git branches, PR Markdown files, and various directories. This lack of a global view makes it difficult to identify blocked tasks, resume in-progress work, and maintain overall operational awareness, forcing costly and error-prone manual investigation.

## 2. Requirements & User Stories (需求定义)
This PRD authorizes the creation of a "Global Control Tower" script that generates a unified dashboard for all projects in the workspace.

**Functional Requirements:**
- **FR1: Workspace Discovery:** The script must automatically scan the `/root/.openclaw/workspace/` directory to discover all valid project folders (defined as directories containing a `.git` folder).
- **FR2: Git State Analysis:** For each discovered project, the script must analyze the Git status to identify the current branch and detect any uncommitted changes. It should specifically identify active feature branches (i.e., not `master` or `main`).
- **FR3: PR Aggregation:** The script must scan a project-local `docs/PRs/` directory (if it exists) to find all PR markdown files and parse their YAML frontmatter to determine their status (`open`, `in_progress`, `closed`, `blocked_fatal`, `superseded`).
- **FR4: Dashboard Generation:** The script must generate a single, human-readable Markdown file named `GLOBAL_KANBAN.md` in the workspace root (`/root/.openclaw/workspace/`). This file will be overwritten on each run.
- **FR5: Actionable Recovery Commands:** For any project with work in progress (e.g., an active feature branch or an `in_progress` PR), the dashboard must provide the exact, copy-pasteable shell command required to resume the SDLC pipeline for that task.

**Non-Functional Requirements:**
- **NFR1: Idempotency:** The script must be stateless and produce the same output given the same workspace state, regardless of how many times it is run.
- **NFR2: Performance:** The script should complete its scan and generation in under 10 seconds for a workspace with up to 10 projects.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
The solution will be a new, self-contained Python script located at `scripts/sync_kanban.py` within the `leio-sdlc` project.

- **Technology Stack:** The script will use standard Python 3 libraries (`os`, `glob`, `subprocess`, `re`) to ensure portability and minimize new dependencies. It will use `subprocess` to call `git` commands and parse their output.
- **Design:** The script will be designed as a stateless, single-pass generator. It will not maintain its own database or state file.
- **Data Flow:**
    1. Scan `/root/.openclaw/workspace/` for subdirectories.
    2. For each directory, check for a `.git` repository.
    3. If it's a Git repo, execute `git status` and `git branch --show-current` to get branch and cleanliness info.
    4. Scan the `docs/PRs/` subdirectory for `.md` files and parse their frontmatter for PR status.
    5. Aggregate all collected data into a structured Python object.
    6. Render this object into a Markdown string and write it to `GLOBAL_KANBAN.md`.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** Healthy multi-project workspace
  - **Given** the workspace contains two projects: `leio-sdlc` (on feature branch `feature/control-tower`) and `AMS` (on `master` with no changes).
  - **And** `leio-sdlc` has a PR file `docs/PRs/PR_Tower.md` with `status: in_progress`.
  - **When** the user executes `python3 /root/.openclaw/skills/leio-sdlc/scripts/sync_kanban.py`.
  - **Then** a `GLOBAL_KANBAN.md` file is created in `/root/.openclaw/workspace/`.
  - **And** the file contains a high-level summary section for `leio-sdlc` indicating "Work in Progress" on branch `feature/control-tower`.
  - **And** the `leio-sdlc` section contains the exact recovery command: `cd /root/.openclaw/workspace/leio-sdlc && python3 /root/.openclaw/skills/leio-sdlc/scripts/orchestrator.py ...`
  - **And** the file contains a section for `AMS` indicating it is "Idle" on branch `master`.

- **Scenario 2:** Workspace with no active work
  - **Given** the workspace contains two projects, both on their `master` branch with no uncommitted changes and no `in_progress` PRs.
  - **When** the user executes `python3 /root/.openclaw/skills/leio-sdlc/scripts/sync_kanban.py`.
  - **Then** `GLOBAL_KANBAN.md` is created.
  - **And** the file indicates both projects are "Idle" with no recovery actions listed.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Quality Goal:** The primary goal is 100% accuracy of the reported state. An incorrect recovery command or status is worse than no report at all.
- **Unit Testing:** Create unit tests (`tests/test_sync_kanban.py`) that test the core parsing logic (Git output parsing, PR frontmatter parsing) in isolation using mock data.
- **E2E Testing:** Create a test script (`scripts/test_sync_kanban.sh`) that builds a temporary mock workspace with a predefined structure (fake projects, git repos, PR files). The script will then run `sync_kanban.py` and `grep` the resulting `GLOBAL_KANBAN.md` to assert that the key information was rendered correctly. This ensures the entire system works from end to end.

## 6. Framework Modifications (框架防篡改声明)
- None. This feature is purely additive.

## 7. Hardcoded Content (硬编码内容)
- **For `GLOBAL_KANBAN.md` (Header and Section Formats)**:
  The script must use the following Markdown structure to ensure consistent parsing by other agents.

  `# 🚀 Global Control Tower: Workspace State`
  `*Last updated: <ISO-8601 Timestamp>*`
  
  `---`
  
  `## 项目: <Project_Name>`
  `- **Status**: <Idle | Work in Progress | Dirty Workspace>`
  `- **Branch**: \`<branch_name>\``
  
  `### Action Required:`
  `\`\`\`bash`
  `<Recovery Command Here if applicable>`
  `\`\`\``
