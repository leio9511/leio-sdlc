#!/bin/bash
# leio-auditor Preflight Check

PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"

echo "[$(date '+%H:%M:%S')] Starting leio-auditor Preflight..."

# Check dependencies
if ! command -v openclaw &> /dev/null; then
    echo "❌ FAILED: 'openclaw' CLI not found."
    exit 1
fi

# Check script health
if [ ! -f "$PROJECT_DIR/scripts/prd_auditor.sh" ]; then
    echo "❌ FAILED: scripts/prd_auditor.sh is missing."
    exit 1
fi

echo "✅ PREFLIGHT SUCCESS: Environment is healthy."
exit 0