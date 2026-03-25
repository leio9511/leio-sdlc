#!/usr/bin/env bash

set -e

echo "Running branch isolation tests..."

# Ensure we are in the leio-sdlc workspace
cd "$(dirname "$0")/.."
WORKSPACE=$(pwd)

# Save current branch
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Cleanup function
cleanup() {
    echo "Cleaning up..."
    git checkout $ORIGINAL_BRANCH || true
    git stash pop -q || true
    git branch -D test_isolation_dummy_branch 2>/dev/null || true
    rm -f dummy_pr.md dummy_prd.md
}
trap cleanup EXIT

# Create dummy files
touch dummy_pr.md dummy_prd.md

# --- Scenario 1: Rejection on Master ---
echo "Scenario 1: Testing rejection on master branch"
git stash push -m "temp_test_stash" && git checkout master || git checkout main

export SDLC_TEST_MODE=true

set +e
OUTPUT=$(python3 scripts/spawn_coder.py --workdir "$WORKSPACE" --pr-file dummy_pr.md --prd-file dummy_prd.md 2>&1)
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 1 ]; then
    echo "❌ Expected exit code 1, got $EXIT_CODE"
    exit 1
fi

if ! echo "$OUTPUT" | grep -q "\[ACTION REQUIRED\]: You must create and checkout a new feature branch before assigning work to the Coder."; then
    echo "❌ Output did not contain expected error message."
    echo "Actual output:"
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 1 passed."

# --- Scenario 2: Acceptance on Feature Branch ---
echo "Scenario 2: Testing acceptance on feature branch"
git checkout -b test_isolation_dummy_branch

set +e
OUTPUT=$(python3 scripts/spawn_coder.py --workdir "$WORKSPACE" --pr-file dummy_pr.md --prd-file dummy_prd.md 2>&1)
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Expected exit code 0, got $EXIT_CODE"
    echo "Actual output:"
    echo "$OUTPUT"
    exit 1
fi

if ! echo "$OUTPUT" | grep -q '"role": "coder"'; then
    echo "❌ Output did not contain expected success message."
    echo "Actual output:"
    echo "$OUTPUT"
    exit 1
fi
echo "✅ Scenario 2 passed."

echo "All branch isolation tests passed!"
