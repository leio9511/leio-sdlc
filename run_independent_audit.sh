#!/bin/bash

cd /root/.openclaw/workspace/projects/leio-sdlc

PRD_CONTENT=$(cat docs/PRDs/PRD_1021_Local_Clone_Concurrency.md)
ORCH_CONTENT=$(cat scripts/orchestrator.py)
SPAWN_CODER=$(cat scripts/spawn_coder.py)

cat << EOF > audit_prompt.txt
You are an independent Senior Architecture Auditor. Your task is to audit a critical proposed architecture upgrade (PRD-1021 v3) for the leio-sdlc orchestrator. 

CONTEXT: The orchestrator currently runs in a single global workspace. We are migrating to a "Local Clone Sandbox" architecture (using git clone --local). 
If this design fails or misses edge cases, the entire CI/CD pipeline breaks.

STEPS:
1. Thoroughly analyze PRD-1021 v3.
2. Cross-reference it against the current orchestrator.py --force-replan true and spawn_coder.py logic.
3. Perform a devastatingly critical analysis. Look for:
   - Hidden Git lock conflicts or race conditions during concurrent runs.
   - Path resolution issues (e.g., orchestrator vs sandbox paths).
   - Any edge cases where the SDLC execution flow will crash, hang, or corrupt the origin repository.

DELIVERABLE: Output a detailed "Architectural Audit Report". Do not hold back. Be ruthlessly critical.

--- PRD-1021 v3 ---
$PRD_CONTENT

--- orchestrator.py --force-replan true ---
$ORCH_CONTENT

--- spawn_coder.py ---
$SPAWN_CODER
EOF

echo "Running independent audit via openclaw agent CLI..."
openclaw agent --session-id prd_1021_independent_auditor --agent gemini --timeout 300 --message "$(cat audit_prompt.txt)"
