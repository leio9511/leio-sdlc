---
Affected_Projects: [leio-sdlc]
---

# PRD: Workspace_Cleanup

## 1. Context & Problem (业务背景与核心痛点)
The `leio-sdlc` workspace currently suffers from severe pollution, containing over 1,200 files. The majority of these are temporary artifacts generated during SDLC runs, tests, and deployments. The most critical issue is an infinite nesting bug (the "Russian doll" effect) caused by deployment and build scripts copying `dist/` into itself (e.g., `dist/dist/root/...`). This pollution has leaked into the production runtime via `kit-deploy.sh`, bloating the system and increasing deployment times.

## 2. Requirements & User Stories (需求定义)
1. **Hard Cleanup**: Physically remove all existing temporary directories, sandbox residuals, and nested deployment folders from the `leio-sdlc` workspace.
2. **Prevent Infinite Nesting**: Fix packaging/deployment scripts (`kit-deploy.sh`, `scripts/build_release.sh`) to explicitly exclude the `dist/` directory (and `.dist/`) from being copied into itself.
3. **Establish Immunity**: Update `.gitignore` and `.release_ignore` to systematically block all known temporary patterns (`.sdlc_runs/`, `dist/`, `.dist/`, `__pycache__/`, `.pytest_cache/`, `.tmp/`, `*.diff`, `*.log`, `.coder_state.json`, `.sdlc_repo.lock`, `.sdlc_lock_manifest.json`, `Review_Report.md`, `pr*.md`, `tmp_pr*.md`, etc.) from being tracked by git or deployed to production.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Target Files**: `.release_ignore`, `.gitignore`, `kit-deploy.sh`, `scripts/build_release.sh`.
- **Cleanup Execution**: Provide a one-off aggressive cleanup script or execute the cleanup directly via PR to reset the workspace to a pristine state.
- **Rule Engine**: Rely on `rsync --exclude-from` and Git's native ignore mechanics to maintain future hygiene. No complex daemon needed.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1:** Running deployment does not nest `dist/`
  - **Given** an existing `dist/` directory with previous build artifacts
  - **When** `kit-deploy.sh` or `build_release.sh` is executed
  - **Then** the new `dist/` directory does not contain another `dist/` inside it.
- **Scenario 2:** Temporary files are ignored by release
  - **Given** SDLC temporary files like `.sdlc_runs/tmp123/`, `.coder_state.json`, and `current_review.diff` exist in the workspace
  - **When** a release package is built or deployed
  - **Then** these temporary files are absent from the target production directory.
- **Scenario 3:** Temporary files are ignored by git
  - **Given** the same SDLC temporary files exist
  - **When** running `git status`
  - **Then** these files do not show up as untracked or modified.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- The primary quality risk is accidentally deleting or ignoring critical source files.
- Use a mock deployment to verify `rsync` behavior without affecting production.
- Validate `.gitignore` by creating dummy `tmp_pr1.md` and `.sdlc_runs/dummy/` and ensuring `git check-ignore` flags them correctly.
- No need to mock external dependencies; test entirely on file system boundaries.

## 6. Framework Modifications (框架防篡改声明)
- `kit-deploy.sh`
- `scripts/build_release.sh`
- `.gitignore`
- `.release_ignore`

## 7. Hardcoded Content (硬编码内容)
### Exact Text Replacements:
- **For `.release_ignore` (Append to file)**:
```text
dist/
.dist/
.sdlc_runs/
__pycache__/
.pytest_cache/
.tmp/
*.diff
*.log
.coder_state.json
.sdlc_repo.lock
.sdlc_lock_manifest.json
Review_Report.md
pr*.md
tmp_pr*.md
```
- **For `.gitignore` (Append to file)**:
```text
dist/
.dist/
.sdlc_runs/
__pycache__/
.pytest_cache/
.tmp/
*.diff
*.log
.coder_state.json
.sdlc_repo.lock
.sdlc_lock_manifest.json
Review_Report.md
pr*.md
tmp_pr*.md
```