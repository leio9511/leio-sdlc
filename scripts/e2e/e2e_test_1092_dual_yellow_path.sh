#!/bin/bash
set -e

# e2e test for ISSUE-1092 Global Dir Fallback

TEST_DIR=$(mktemp -d)
echo "Setting up test workspace in $TEST_DIR"

cd "$TEST_DIR"
git init > /dev/null
echo "Affected_Projects: [mock_project]" > PRD.md
git add PRD.md
git commit -m "init" > /dev/null

export SDLC_TEST_MODE="true"

# The scripts path
SDLC_ROOT="/root/.openclaw/workspace/projects/leio-sdlc"

echo "Testing spawn_planner.py without --global-dir..."
python3 "$SDLC_ROOT/scripts/spawn_planner.py" --workdir "$TEST_DIR" --prd-file PRD.md

echo "Checking if .sdlc_runs is created in workdir..."
if [ -d "$TEST_DIR/.sdlc_runs" ]; then
    echo "PASS: spawn_planner.py created .sdlc_runs in workdir"
else
    echo "FAIL: spawn_planner.py did not create .sdlc_runs in workdir"
    exit 1
fi

echo "Testing orchestrator.py without --global-dir..."
python3 "$SDLC_ROOT/scripts/orchestrator.py" --workdir "$TEST_DIR" --prd-file PRD.md --force-replan false --test-sleep --enable-exec-from-workspace --channel test_channel

echo "PASS: orchestrator.py did not raise RuntimeError"

rm -rf "$TEST_DIR"
echo "All tests passed."
