status: closed

# PR-001: Global Run State Directory & Stateless File I/O Tracking

## 1. Objective
Refactor the planner and orchestrator to use a global, Git-ignored run state directory grouped by project, and transition PR status tracking to pure file I/O.

## 2. Scope (Functional & Implementation Freedom)
- Implement logic to save generated PR slices into a global run state directory (`/root/.openclaw/workspace/.sdlc_runs/<PRD_Name>/`), grouped by target project.
- Refactor the orchestrator to iterate through these project-specific folders and resolve the effective working directory.
- Update the PR status tracking mechanism to rely entirely on pure file I/O, removing any legacy Git add/commit commands previously used for this purpose.
*The Coder MUST search the workspace, understand the existing code structure, and autonomously decide which files to create or modify to implement this logic.*

## 3. TDD & Acceptance Criteria
- PR slices are successfully generated and saved in the correct project-grouped directory structure under `.sdlc_runs`.
- The orchestrator can correctly discover and iterate over these project folders.
- PR status updates (e.g., open to done) are persisted correctly to the file system without executing Git commits.
- All relevant integration tests are updated and pass (GREEN).