---
Affected_Projects: [leio-sdlc, pm-skill, leio-auditor]
---

# PRD: Universal Triad Adaptation & Toolchain Deployment

## 1. Context & Problem Definition (核心问题与前因后果)
Currently, the SDLC ecosystem suffers from **"Agentic Microservices Sprawl"**. We have successfully completed Phase 1 of the migration: physically moving the `pm-skill` and `leio-auditor` source code into the `leio-sdlc/skills/` directory and stripping their independent Git histories to form a cohesive **"Toolchain Monorepo"**.

However, Phase 2 (Code Refactoring & Deployment Pipeline) remains pending. The current issues are:
1. **LLM Driver Coupling:** `leio-auditor` still hardcodes `openclaw agent --message ...` via a Bash script (`prd_auditor.sh`). This prevents running it on environments with pure standalone LLM CLIs (e.g., `gemini` CLI) and exposes it to global prompt pollution ("Clone Identity Crisis").
2. **Production Deployment Crashing (ModuleNotFoundError):** While developing in the Monorepo, skills might try to use relative imports to share `agent_driver.py`. But when deployed to `~/.openclaw/skills/` via hard copy, they become physically isolated folders. A relative import will crash the production environment.

## 2. Requirements (需求说明)
The Orchestrator, PM, and Auditor MUST remain three distinct, independent tools (Triad Consensus Loop). To finalize the Toolchain Monorepo, the SDLC Coder must execute the following updates:

1. **Python Rewrite for Auditor & PM Import Fixes:**
   - Rewrite `skills/leio-auditor/scripts/prd_auditor.sh` into `skills/leio-auditor/scripts/prd_auditor.py`.
   - Ensure the `pm-skill` executable script is physically located at `skills/pm-skill/scripts/pm.py` (migrated from the root `scripts/pm.py`).
   - BOTH `skills/leio-auditor/scripts/prd_auditor.py` and `skills/pm-skill/scripts/pm.py` MUST utilize `leio-sdlc/scripts/agent_driver.py`.
   - **CRITICAL IMPORT FIX:** Update the Python `sys.path` logic within `pm.py` and `prd_auditor.py` to dynamically resolve the `agent_driver.py` module. During development in the Monorepo, it must resolve to `../../../scripts/agent_driver.py`. During production deployment (where `agent_driver.py` is copied into each skill's `scripts/` directory), it must resolve locally.
   - The prompts must be loaded cleanly from `leio-sdlc/config/prompts.json` (under an "auditor" and "pm" key) to eliminate the "Clone Identity Crisis".
2. **Atomic Deployment Script Fix (Crucial for Production):**
   - Update the root `leio-sdlc/deploy.sh` script (or create one if it only deploys the orchestrator). The deployment pipeline MUST iterate through all skills in `leio-sdlc/skills/` (`pm-skill`, `leio-auditor`).
   - During deployment to `~/.openclaw/skills/<skill_name>`, the deploy script MUST physically copy `leio-sdlc/scripts/agent_driver.py` and `leio-sdlc/config/prompts.json` into each skill's respective deployment directory (e.g., `scripts/` and `config/`).
   - This guarantees that in production, each skill remains a 100% self-contained bundle, strictly preventing `ModuleNotFoundError` when importing `agent_driver.py`.

## 3. Architecture (架构设计)
- **Triad Consensus Loop:** Maintains the Orchestrator, PM, and Auditor as distinct entities.
- **Shared LLM Driver:** Extracts the LLM invocation logic into a shared `agent_driver.py` that can handle multiple CLI drivers (openclaw, gemini).
- **Isolated Deployment:** The deployment script resolves the monorepo-to-production impedance mismatch. Instead of relying on symlinks or relative imports that break outside the monorepo, the deployer statically injects `agent_driver.py` and `prompts.json` into each skill's distribution bundle during installation to `~/.openclaw/skills/`.

## 4. Acceptance Criteria (验收标准)
- [ ] `skills/leio-auditor/scripts/prd_auditor.py` is created, replacing the bash script, and invokes `agent_driver.py` natively.
- [ ] `skills/pm-skill/scripts/pm.py` uses `sys.path` logic to correctly import `agent_driver.py` in both monorepo development and production paths.
- [ ] `leio-sdlc/config/prompts.json` is updated to contain the Red Team Auditor prompt and PM prompt.
- [ ] The deployment process automatically packages `agent_driver.py` and `prompts.json` into the target directory of both `pm-skill` and `leio-auditor` during deployment.
- [ ] When fully deployed to `~/.openclaw/skills/`, executing `pm.py` or `prd_auditor.py` from any directory successfully loads the driver and config without relative import crashes.

## 5. Framework Modifications (框架修改声明)
- `skills/leio-auditor/SKILL.md` (modified)
- `skills/pm-skill/SKILL.md` (modified)
- `skills/leio-auditor/scripts/prd_auditor.sh` (deleted)
- `skills/leio-auditor/scripts/prd_auditor.py` (created)
- `skills/pm-skill/scripts/pm.py` (modified)
- `leio-sdlc/config/prompts.json` (modified)
- `leio-sdlc/deploy.sh` (modified/created)

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
> **[CRITICAL INSTRUCTION FOR PLANNER & CODER]**
> IGNORING THIS SECTION IS MANDATORY. This section is strictly for historical tracking of the PM-Auditor-Boss discussion loop. Do NOT read, reference, or implement any logic from this appendix into the SDLC pipeline.

- **v1.0**: Initial PRD drafted to address Agentic Microservices Sprawl and resolve deployment crashes caused by relative imports of `agent_driver.py`.
- **v1.1**: Added explicit requirement to fix `sys.path` import logic in `pm.py` and `prd_auditor.py` to support dual-mode execution (Monorepo Development vs. Production Isolation). Included `pm.py` in Framework Modifications.
