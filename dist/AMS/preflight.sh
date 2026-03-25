#!/bin/bash
PROJECT_DIR=$(dirname "$0")
LOG_FILE="$PROJECT_DIR/build_preflight.log"

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1
PYTHONPATH=. pytest tests/ > "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ PREFLIGHT SUCCESS: Code compiled and all Unit/Probe tests passed."
    rm -f "$LOG_FILE"
    exit 0
else
    echo "❌ PREFLIGHT FAILED (Exit Code: $EXIT_CODE)!"
    grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$LOG_FILE" | head -n 50
    exit $EXIT_CODE
fi
