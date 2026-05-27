#!/usr/bin/env bash
set -e

echo "================================================="
echo "Testing: Reviewer Workdir Propagation"
echo "================================================="

export SDLC_TEST_MODE=true
WORK_DIR=$(mktemp -d)
REPO_DIR=$(pwd)

# Test 1: Reviewer
echo "Running Test Scenario 1 (Reviewer)..."
touch "$WORK_DIR/dummy_pr.md"
OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_reviewer.py" --enable-exec-from-workspace --pr-file "$WORK_DIR/dummy_pr.md" --diff-target HEAD --workdir "$WORK_DIR" --engine openclaw 2>&1 || true)
if echo "$OUTPUT" | grep -q '\[FATAL\] direct_cli engine with workspace_arg requires explicit workdir'; then
    echo "❌ Scenario 1 Failed: Reviewer hit workdir fatal error."
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 1 Passed."

rm -rf "$WORK_DIR"
echo "✅ test_reviewer_workdir_propagation.sh passed."
exit 0
