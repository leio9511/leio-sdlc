#!/bin/bash
# test_runtime_boundary_allowed.sh
# Executes orchestrator.py WITH --enable-exec-from-workspace.
# Must bypass path check (which will be implemented in PR-002) and fail on missing required arguments, not unrecognized argument.

SCRIPT_DIR=$(dirname "$0")
ORCHESTRATOR_PATH="$SCRIPT_DIR/../scripts/orchestrator.py"

# Capture output
OUTPUT=$(python3 "$ORCHESTRATOR_PATH" --enable-exec-from-workspace 2>&1)
EXIT_CODE=$?

# It should fail because required arguments (--workdir, --prd-file) are missing, so exit code should be 2 from argparse
if [ $EXIT_CODE -eq 2 ]; then
    if echo "$OUTPUT" | grep -q "unrecognized arguments: --enable-exec-from-workspace"; then
        echo "FAIL: Unrecognized argument error."
        exit 1
    else
        echo "PASS: Allowed correctly (failed on missing required args as expected)."
        exit 0
    fi
else
    echo "FAIL: Expected exit code 2, got $EXIT_CODE"
    echo "Actual output:"
    echo "$OUTPUT"
    exit 1
fi
