#!/bin/bash
set -e

echo "--- Running Orchestrator File Logging Test ---"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"

# Create a dummy PRD and required structure
mkdir -p docs/PRDs
echo "dummy prd content" > docs/PRDs/dummy.md

# Initialize Git to pass boundary check
git init > /dev/null
git add docs/PRDs/dummy.md
echo "test_output.log" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
git add .gitignore
git commit -m "init" > /dev/null

# Create .sdlc_runs/dummy/PR_001.md with in_progress status
mkdir -p .sdlc_runs/dummy
echo -e "status: in_progress\nslice_depth: 1" > .sdlc_runs/dummy/PR_001.md

# Run orchestrator
export PYTHONPATH="${PROJECT_ROOT}/scripts:$PYTHONPATH"
export SDLC_BYPASS_BRANCH_CHECK=1
export SDLC_TEST_MODE=true
set +e
# Use timeout to avoid hang if it tries to spawn something
timeout 15 python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --max-prs-to-process 1 --force-replan false --channel "valid:id" > test_output.log 2>&1
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
LOG_FILE=$(ls $LOG_DIR/orchestrator_*.log 2>/dev/null | head -n 1)
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
rm -rf "$SANDBOX_DIR"
exit 0
