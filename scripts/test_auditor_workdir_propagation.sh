#!/usr/bin/env bash
set -e

echo "================================================="
echo "Testing: Auditor Workdir Propagation"
echo "================================================="

export SDLC_TEST_MODE=true
WORK_DIR=$(mktemp -d)
REPO_DIR=$(pwd)

echo "Running Test Scenario 1 (Auditor)..."
touch "$WORK_DIR/dummy_prd.md"
OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_auditor.py" --enable-exec-from-workspace --prd-file "$WORK_DIR/dummy_prd.md" --workdir "$WORK_DIR" --channel dummy_channel --engine openclaw 2>&1 || true)
if echo "$OUTPUT" | grep -q '\[FATAL\] direct_cli engine with workspace_arg requires explicit workdir'; then
    echo "❌ Scenario 1 Failed: Auditor hit workdir fatal error."
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 1 Passed."

echo "Running Test Scenario 2 (Auditor Help Output)..."
HELP_OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_auditor.py" --help)
if ! echo "$HELP_OUTPUT" | grep -q "agy"; then
    echo "❌ Scenario 2 Failed: 'agy' not found in dynamic engine choices."
    exit 1
fi
echo "✅ Scenario 2 Passed."

rm -rf "$WORK_DIR"
echo "✅ test_auditor_workdir_propagation.sh passed."
exit 0
