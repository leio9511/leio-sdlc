#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)
# Usage: Copy this to the root of any new project as `preflight.sh`
# and modify the "RUN_COMMAND" section for the specific tech stack.

PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

# --- 1. MODIFY THIS SECTION FOR YOUR STACK ---
cd "$PROJECT_DIR" || exit 1

# Execute all unit/E2E test scripts
(
    set -e
    echo "Running Create PR Contract Engine Tests..."
    bash scripts/test_create_pr_contract.sh

    echo "Running Job Queue Engine Tests..."
    bash scripts/test_job_queue_engine.sh
    echo "Running CWD Guardrail Tests..."
    bash scripts/test_cwd_guardrail.sh
    
    echo "Running Anti-Reward Hacking Tests..."
    bash scripts/test_anti_reward_hacking.sh

    echo "Running Preflight Guardrails Tests..."
    echo "Running Manager Queue Polling E2E Tests..."
    bash scripts/test_manager_queue_polling.sh
    bash scripts/test_preflight_guardrails.sh
    
    echo "Running Planner Micro-Slicing Act Tests..."
    bash scripts/test_planner_micro_slicing.sh
    
    echo "Running Planner Slice Failed PR Tests..."
    bash scripts/test_planner_slice_failed_pr.sh
    
    echo "Running Build Release Tests..."
    bash scripts/test_build_release.sh
    
    echo "Running Branch Isolation Tests..."
    bash scripts/test_branch_isolation.sh
    
    echo "Running Blue/Green Deploy Tests..."
    echo "Running Clean Workspace Escalation Tests..."
    bash scripts/test_escalation_clean.sh

    echo "Running Reviewer Artifact Guardrail Tests..."
    bash scripts/test_reviewer_artifact_guardrail.sh
    bash scripts/test_deploy_hardcopy.sh
    
    echo "Running Orchestrator FSM Sandbox Tests..."
    bash scripts/test_orchestrator_fsm.sh

    echo "Running Orchestrator Session Strategy Tests..."
    bash scripts/test_orchestrator_session_strategy.sh

    echo "Running Orchestrator Missing Channel Test..."
    bash scripts/test_missing_channel.sh

    echo "Running Orchestrator Missing Force-Replan Test..."
    bash scripts/test_missing_force_replan.sh

    echo "Running Orchestrator GitHub Sync Test..."
    bash scripts/test_github_sync_integration.sh

    echo "Running Pre-Commit Hook Test..."
    bash scripts/test_pre_commit_hook.sh
    
    echo "Running Triad Agent Driver Tests..."
    python3 tests/test_triad_agent_driver.py
    echo "Running offline syntax check for agent_driver.py..."
    python3 -m py_compile scripts/agent_driver.py

    echo "Running Cleanup Quarantine Test..."
    python3 tests/test_cleanup_flag.py
) > "$LOG_FILE" 2>&1
# ---------------------------------------------

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ PREFLIGHT SUCCESS: Code compiled and all Unit/Probe tests passed."
    rm -f "$LOG_FILE"
    exit 0
else
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    # Extract only lines containing Error, Exception, FAILED, or specific stacktraces
    # Adjust grep patterns based on the language/framework stack
    grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi

