#!/usr/bin/env bash
set -euo pipefail

TEST_NAME="test_planner_slice"
TEST_DIR=""
SANDBOX_NAME=""
GLOBAL_MOCK_DIR=""

setup_sandbox() {
    local sandbox_name="$1"

    : "${GLOBAL_MOCK_DIR:?GLOBAL_MOCK_DIR must be initialized before setup_sandbox}"

    TEST_DIR="$(mktemp -d "/tmp/${sandbox_name}.XXXXXX")"
    SANDBOX_NAME="$(basename "$TEST_DIR")"
    WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    cp -r "$WORKSPACE_ROOT/." "$TEST_DIR/"
    cd "$TEST_DIR"
    export PYTHONPATH="$TEST_DIR"
    export WORKSPACE_DIR="$TEST_DIR"
    mkdir -p docs/PRDs tests "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD"
}

cleanup() {
    if [[ -n "${TEST_DIR:-}" && -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
    if [[ -n "${GLOBAL_MOCK_DIR:-}" && -d "$GLOBAL_MOCK_DIR" ]]; then
        rm -rf "$GLOBAL_MOCK_DIR"
    fi
}

trap cleanup EXIT

echo "================================================="
echo "Testing: Planner Micro-Slicing Logic"
echo "================================================="

# Initialize GLOBAL_MOCK_DIR as a runner-safe temporary directory before sandbox setup
GLOBAL_MOCK_DIR="$(mktemp -d "/tmp/mock_sdlc_global.XXXXXX")"
export GLOBAL_MOCK_DIR
setup_sandbox "$TEST_NAME"
export SDLC_TEST_MODE=true

# Test Scenario 5: Bootstrap Safety Regression
echo "Running Test Scenario 5 (Bootstrap Safety Regression)..."
EXPECTED_MOCK_PR_DIR="$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD"
if [[ -z "$GLOBAL_MOCK_DIR" ]]; then
    echo "❌ Scenario 5 Failed: GLOBAL_MOCK_DIR was not initialized before sandbox setup."
    exit 1
fi
if [[ ! -d "$EXPECTED_MOCK_PR_DIR" ]]; then
    echo "❌ Scenario 5 Failed: Expected mock PR directory was not created under GLOBAL_MOCK_DIR."
    exit 1
fi
case "$EXPECTED_MOCK_PR_DIR" in
    /tmp/*) ;;
    *)
        echo "❌ Scenario 5 Failed: Mock PR directory escaped the runner-safe temporary location."
        exit 1
        ;;
esac
echo "✅ Scenario 5 Passed."

# Create a mock PRD
printf '# Mock PRD\n' > PRD.md

# Test Scenario 1: Regression (Happy Path)
echo "Running Test Scenario 1 (Regression)..."
python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file PRD.md --workdir . --global-dir "$GLOBAL_MOCK_DIR"
ls -lR "$GLOBAL_MOCK_DIR/.sdlc_runs"
if [[ ! -f "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD/PR_A.md" || ! -f "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD/PR_B.md" ]]; then
    echo "❌ Scenario 1 Failed: Expected mock PRs not created."
    exit 1
fi
echo "✅ Scenario 1 Passed."

# Test Scenario 2: File Missing
echo "Running Test Scenario 2 (File Missing)..."
if python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file PRD.md --workdir . --global-dir "$GLOBAL_MOCK_DIR" --slice-failed-pr fake.md > error_log.txt 2>&1; then
    ls -lR "$GLOBAL_MOCK_DIR/.sdlc_runs"
    echo "❌ Scenario 2 Failed: Expected script to exit with error."
    exit 1
fi
if ! grep -q "\[Pre-flight Failed\]" error_log.txt; then
    echo "❌ Scenario 2 Failed: Missing '[Pre-flight Failed]' error message."
    exit 1
fi
echo "✅ Scenario 2 Passed."

# Test Scenario 3: Successful Slice
echo "Running Test Scenario 3 (Successful Slice)..."
printf '# Failed PR content\n' > PR_001_Failed_PR.md
python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file PRD.md --workdir . --global-dir "$GLOBAL_MOCK_DIR" --slice-failed-pr PR_001_Failed_PR.md
ls -lR "$GLOBAL_MOCK_DIR/.sdlc_runs"
if [[ ! -f "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD/PR_Slice_1.md" || ! -f "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/PRD/PR_Slice_2.md" ]]; then
    echo "❌ Scenario 3 Failed: Expected mock slice PRs not created."
    exit 1
fi
if ! grep -q -- "--insert-after 001" tests/task_string.log; then
    echo "❌ Scenario 3 Failed: Missing '--insert-after 001' in task string."
    exit 1
fi
FAILED_PR_001_ABS="$(pwd)/PR_001_Failed_PR.md"
if ! grep -q "failed_pr_contract" tests/task_string.log; then
    echo "❌ Scenario 3 Failed: Missing failed_pr_contract reference in task string."
    exit 1
fi
if ! grep -q "$FAILED_PR_001_ABS" tests/task_string.log; then
    echo "❌ Scenario 3 Failed: Missing absolute failed PR contract path in task string."
    exit 1
fi
if ! grep -q '"required": true' tests/task_string.log; then
    echo "❌ Scenario 3 Failed: Missing required=true in task string."
    exit 1
fi
if ! grep -q '"priority": 1' tests/task_string.log; then
    echo "❌ Scenario 3 Failed: Missing priority=1 in task string."
    exit 1
fi
echo "✅ Scenario 3 Passed."

# Test Scenario 4: Successful Slice with sub-id
echo "Running Test Scenario 4 (Successful Slice with sub-id)..."
printf '# Failed PR content\n' > PR_002_1_Failed_PR.md
python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file PRD.md --workdir . --global-dir "$GLOBAL_MOCK_DIR" --slice-failed-pr PR_002_1_Failed_PR.md
ls -lR "$GLOBAL_MOCK_DIR/.sdlc_runs"
if ! grep -q -- "--insert-after 002_1" tests/task_string.log; then
    echo "❌ Scenario 4 Failed: Missing '--insert-after 002_1' in task string."
    cat tests/task_string.log
    exit 1
fi
FAILED_PR_002_1_ABS="$(pwd)/PR_002_1_Failed_PR.md"
if ! grep -q "$FAILED_PR_002_1_ABS" tests/task_string.log; then
    echo "❌ Scenario 4 Failed: Missing absolute failed PR contract path in task string."
    cat tests/task_string.log
    exit 1
fi
echo "✅ Scenario 4 Passed."

echo "✅ test_planner_slice_failed_pr.sh passed."
exit 0
