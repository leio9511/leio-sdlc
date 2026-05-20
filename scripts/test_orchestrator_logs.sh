#!/bin/bash
set -euo pipefail

echo "--- Running Orchestrator File Logging Test ---"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
SANDBOX_DIR=$(mktemp -d)
GLOBAL_MOCK_DIR=$(mktemp -d)
trap 'rm -rf "$SANDBOX_DIR" "$GLOBAL_MOCK_DIR"' EXIT
cd "$SANDBOX_DIR"

# Simulate a clean runner by preventing fallback to host git config.
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
unset GIT_AUTHOR_NAME
unset GIT_AUTHOR_EMAIL
unset GIT_COMMITTER_NAME
unset GIT_COMMITTER_EMAIL

# Create a dummy PRD and required structure
mkdir -p docs/PRDs
echo "dummy prd content" > docs/PRDs/dummy.md

# Initialize Git to pass boundary check
source "${PROJECT_ROOT}/scripts/e2e/setup_sandbox.sh"
init_git_test_sandbox "$(pwd)"
if [ "$(git config --local --get user.name)" != "SDLC Test Sandbox" ] || [ "$(git config --local --get user.email)" != "sdlc-test-sandbox@example.invalid" ]; then
    echo "❌ test_orchestrator_logs.sh FAILED: Sandbox repo-local git identity was not configured correctly."
    exit 1
fi

# Apply SDLC infrastructure
"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1

echo "test_output.log" >> .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo ".tmp" >> .gitignore
git add docs/PRDs/dummy.md .gitignore STATE.md preflight.sh
git commit -m "init" > /dev/null

if ! git rev-parse --verify HEAD > /dev/null 2>&1; then
    echo "❌ test_orchestrator_logs.sh FAILED: Sandbox git bootstrap did not produce an initial commit."
    exit 1
fi

# Create .sdlc_runs/dummy/PR_001.md with in_progress status
SANDBOX_NAME="$(basename "$SANDBOX_DIR")"
mkdir -p "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/dummy"
git rev-parse HEAD > "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/dummy/baseline_commit.txt"
echo -e "status: in_progress\nslice_depth: 1" > "$GLOBAL_MOCK_DIR/.sdlc_runs/$SANDBOX_NAME/dummy/PR_001.md"

# Run orchestrator
export PYTHONPATH="${PROJECT_ROOT}/scripts:${PYTHONPATH:-}"
export SDLC_BYPASS_BRANCH_CHECK=1
export SDLC_TEST_MODE=true
set +e
# Use timeout to avoid hang if it tries to spawn something
timeout 15 "$DEV_PYTHON" "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --max-prs-to-process 1 --force-replan false --channel "valid:id" --global-dir "$GLOBAL_MOCK_DIR" > test_output.log 2>&1
EXIT_CODE=$?
set -e

# Check if logs directory was created
LOG_DIR=".tmp/sdlc_logs"
if [ ! -d "$LOG_DIR" ]; then
    echo "❌ test_orchestrator_logs.sh FAILED: Log directory $LOG_DIR not found."
    echo "--- Orchestrator Output ---"
    cat test_output.log
    exit 1
fi

# Check if a log file exists
LOG_FILE=$(ls "$LOG_DIR"/orchestrator_*.log 2>/dev/null | head -n 1)
if [ -z "$LOG_FILE" ]; then
    echo "❌ test_orchestrator_logs.sh FAILED: No log file found in $LOG_DIR."
    exit 1
fi

echo "Found log file: $LOG_FILE"

# Check for debug logs from the scanning block
if ! grep -q "Scanning job_dir" "$LOG_FILE"; then
    echo "❌ test_orchestrator_logs.sh FAILED: 'Scanning job_dir' not found in log file."
    echo "--- Log Content ---"
    cat "$LOG_FILE"
    exit 1
fi

echo "✅ test_orchestrator_logs.sh PASSED"
exit 0

