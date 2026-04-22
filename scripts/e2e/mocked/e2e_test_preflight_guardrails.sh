#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

echo "Starting Pre-flight Guardrails Test..."

# 1. Initialize Sandbox
TEST_DIR=$(mktemp -d -t sdlc_guardrails_test_XXXXXX)
echo "Sandbox created at $TEST_DIR"

init_hermetic_sandbox "$TEST_DIR/scripts"

cd "$TEST_DIR"
git init >/dev/null 2>&1
git config user.email "test@example.com"
git config user.name "Test User"
git commit --allow-empty -m "init" >/dev/null 2>&1

export SDLC_TEST_MODE=true

# 2. Test Planner Pre-flight
echo "Testing Planner Pre-flight..."
set +e
output=$(python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file missing.md --workdir . --global-dir . 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Planner exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Planner did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# 3. Test Coder Pre-flight
echo "Testing Coder Pre-flight..."
git checkout -b feature/dummy-guardrails >/dev/null 2>&1
set +e
output=$(python3 scripts/spawn_coder.py --enable-exec-from-workspace --pr-file missing.md --prd-file missing.md --workdir . --global-dir . 2>&1)
exit_code=$?
set -e
git checkout master >/dev/null 2>&1
if [ $exit_code -ne 1 ]; then
    echo "Fail: Coder exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Coder did not output [Pre-flight Failed]"
    echo "Output was: $output"
    exit 1
fi

# 4. Test Reviewer Pre-flight
echo "Testing Reviewer Pre-flight..."
# Create a dummy PR file to satisfy file check, but it should still fail status check or logic
echo "---
status: open
---" > PR.md
set +e
output=$(python3 scripts/spawn_reviewer.py --enable-exec-from-workspace --pr-file PR.md --diff-target HEAD --workdir . --global-dir . 2>&1)
exit_code=$?
set -e

# 5. Test Merge Pre-flight
echo "Testing Merge Pre-flight..."
# Action 1: fake review file
set +e
output=$(python3 scripts/merge_code.py --branch fake-branch --review-file missing.md 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Merge exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Merge did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# Action 2: {"overall_assessment": "NEEDS_IMMEDIATE_REWORK"} without force
echo '{"overall_assessment": "NEEDS_IMMEDIATE_REWORK"}' > review.md
set +e
output=$(python3 scripts/merge_code.py --branch fake-branch --review-file review.md 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Merge exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Merge did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# Action 3: {"overall_assessment": "NEEDS_IMMEDIATE_REWORK"} with force
echo "Testing Merge with force-approved..."
set +e
python3 scripts/merge_code.py --branch fake-branch --review-file review.md --force-approved >/dev/null 2>&1
exit_code=$?
set -e
if [ $exit_code -ne 0 ]; then
    echo "Fail: Merge should have succeeded with force-approved"
    exit 1
fi

# Action 4: {"overall_assessment": "EXCELLENT"}
echo "Testing Merge with APPROVED..."
echo '{"overall_assessment": "EXCELLENT"}' > review2.md
set +e
python3 scripts/merge_code.py --branch fake-branch --review-file review2.md >/dev/null 2>&1
exit_code=$?
set -e
if [ $exit_code -ne 0 ]; then
    echo "Fail: Merge should have succeeded with APPROVED"
    exit 1
fi

# 6. Cleanup Sandbox
echo "[GUARDRAILS_TEST_SUCCESS]"
rm -rf "$TEST_DIR"
