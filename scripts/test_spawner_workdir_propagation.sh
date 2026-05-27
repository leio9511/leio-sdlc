#!/usr/bin/env bash
set -e

echo "================================================="
echo "Testing: Spawner Workdir Propagation & Engine Flags"
echo "================================================="

export SDLC_TEST_MODE=true
WORK_DIR=$(mktemp -d)
REPO_DIR=$(pwd)

# Test 1: Auditor
echo "Running Test Scenario 1 (Auditor)..."
# The script will likely exit 1 because /dev/null is empty or not a valid PRD, but it shouldn't be the FATAL workdir error
OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_auditor.py" --enable-exec-from-workspace --prd-file /dev/null --workdir "$WORK_DIR" --engine openclaw 2>&1 || true)
if echo "$OUTPUT" | grep -q '\[FATAL\] direct_cli engine with workspace_arg requires explicit workdir'; then
    echo "❌ Scenario 1 Failed: Auditor hit workdir fatal error."
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 1 Passed."

# Test 2: Planner
echo "Running Test Scenario 2 (Planner)..."
OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_planner.py" --enable-exec-from-workspace --prd-file /dev/null --workdir "$WORK_DIR" --engine openclaw 2>&1 || true)
if echo "$OUTPUT" | grep -q '\[FATAL\] direct_cli engine with workspace_arg requires explicit workdir'; then
    echo "❌ Scenario 2 Failed: Planner hit workdir fatal error."
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 2 Passed."

# Test 3: Reviewer
echo "Running Test Scenario 3 (Reviewer)..."
touch "$WORK_DIR/dummy_pr.md"
OUTPUT=$(python3 "$REPO_DIR/scripts/spawn_reviewer.py" --enable-exec-from-workspace --pr-file "$WORK_DIR/dummy_pr.md" --diff-target HEAD --workdir "$WORK_DIR" --engine openclaw 2>&1 || true)
if echo "$OUTPUT" | grep -q '\[FATAL\] direct_cli engine with workspace_arg requires explicit workdir'; then
    echo "❌ Scenario 3 Failed: Reviewer hit workdir fatal error."
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 3 Passed."

# Test 4: Help menus contain agy choice
echo "Running Test Scenario 4 (Help text)..."
if ! python3 "$REPO_DIR/scripts/spawn_auditor.py" --help | grep -E -q "agy"; then
    echo "❌ Scenario 4 Failed: spawn_auditor.py --help missing agy."
    python3 "$REPO_DIR/scripts/spawn_auditor.py" --help
    exit 1
fi

if ! python3 "$REPO_DIR/scripts/spawn_planner.py" --help | grep -E -q "agy"; then
    echo "❌ Scenario 4 Failed: spawn_planner.py --help missing agy."
    exit 1
fi
echo "✅ Scenario 4 Passed."

rm -rf "$WORK_DIR"
echo "✅ test_spawner_workdir_propagation.sh passed."
exit 0