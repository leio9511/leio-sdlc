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
# Examples: 
# Android: ./gradlew assembleDebug testDebugUnitTest
# AgentSkill: 
#   ./scripts/probe_test.sh (Standard Logic Probes)
#   ./scripts/agentic_smoke_test.sh (Agent-to-Agent E2E Test)
cd "$PROJECT_DIR" || exit 1
# RUN_COMMAND_HERE > "$LOG_FILE" 2>&1
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
    grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback" "$LOG_FILE" | head -n 50
    echo "==============================================================="
    echo "Please fix the code above to pass the preflight gate."
    exit $EXIT_CODE
fi
