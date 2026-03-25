#!/bin/bash

PLAN_PATH="/root/.openclaw/workspace/projects/leio-sdlc/polyrepo_plan.md"
PRD_PATH="/root/.openclaw/workspace/projects/leio-sdlc/docs/PRDs/PRD_1022_Polyrepo_Compatibility.md"

cat << EOF > audit_instruction.txt
You are an independent Senior Architecture Auditor. Your task is to perform a FINAL audit on the implementation plan for the "Hub & Spoke Polyrepo" migration.

CONTEXT: We are splitting the monolithic workspace into multiple independent Git repositories (Polyrepo). The previous PRD-1022 v3 failed due to CWE-377 (predictable /tmp filenames), E2BIG limit circumvention bugs, and Zombie files left on disk after agent spawns.
We have now authored PRD-1022 v4 which mandates Python's tempfile.mkstemp(), strict 0o600 permissions, and try...finally cleanup wrappers.

STEPS:
1. Read the Polyrepo architectural plan at: $PLAN_PATH
2. Read the mitigation PRD at: $PRD_PATH
3. Perform a devastatingly critical analysis of PRD-1022 v4 against the Polyrepo plan. Look for:
   - Does "Secure Temporary Prompt Injection" fully remediate the vulnerabilities highlighted in v6 (CWE-377, Filename Collision, Zombie File Accumulation)?
   - Will the use of try...finally ensure disk cleanup even if the openclaw agent crashes or is killed by a timeout?
   - Is the overall Orchestrator architecture finally robust enough for Polyrepo separation?

DELIVERABLE: Output a detailed "Architectural Audit Report v7". If the architecture is secure and robust, you MUST output the literal string: [LGTM]
If it is not, fail it with a detailed explanation.
EOF

openclaw agent --session-id polyrepo_native_auditor_05 --timeout 600 --message "$(cat audit_instruction.txt)"