#!/bin/bash
# SDLC_MANAGED_HOOK=leio-sdlc
# SDLC_HOOK_SCHEMA_VERSION=2
# leio-sdlc standard pre-commit hook payload
# Part of PRD-1012 / PR-002: Role-Aware Runtime Hook Allowlist Enforcement
#
# This payload is the managed hook source installed via install_hook.sh
# or doctor.py. It enforces role-aware allowlist authorization for runtime commits.

# 1. Opt-in Guardrail
if [ ! -f .sdlc_guardrail ]; then
    exit 0
fi

# 2. Scope Protection: ONLY master or main branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "master" && "$CURRENT_BRANCH" != "main" ]]; then
    exit 0
fi

# 3. Authentication via Native Git Configuration
SDLC_RUNTIME=$(git config sdlc.runtime || echo "0")
SDLC_OVERRIDE=$(git config sdlc.override || echo "false")
SDLC_ROLE=$(git config sdlc.role || echo "")

if [[ "$SDLC_OVERRIDE" == "true" ]]; then
    exit 0
fi

if [[ "$SDLC_RUNTIME" == "1" ]]; then
    if [[ -z "$SDLC_ROLE" ]]; then
        echo "❌ Commit rejected: runtime commit requires explicit sdlc.role."
        exit 1
    fi

    case "$SDLC_ROLE" in
        coder|orchestrator|merge_code|commit_state)
            exit 0
            ;;
        *)
            echo "❌ Commit rejected: SDLC runtime role '$SDLC_ROLE' is not authorized to commit."
            exit 1
            ;;
    esac
fi

# 4. Glass-Break Emergency Override & JIT Prompt Enforcement
echo "==============================================================="
echo "❌ GIT COMMIT REJECTED ON PROTECTED BRANCH: $CURRENT_BRANCH"
echo "==============================================================="
echo "Role Awakening: As a Manager, you should NEVER commit directly!"
echo "Please use the official gateway to baseline your state/PRD before pipeline ignition:"
echo "python3 ${SDLC_SKILLS_ROOT:-~/.openclaw/skills}/leio-sdlc/scripts/commit_state.py --files <path_to_files>"
echo "==============================================================="

exit 1
