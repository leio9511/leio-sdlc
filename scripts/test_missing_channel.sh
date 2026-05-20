#!/bin/bash
set -e

echo "--- Running Missing Channel Test ---"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"

# Simulate a clean runner by preventing fallback to host git config.
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
unset GIT_AUTHOR_NAME
unset GIT_AUTHOR_EMAIL
unset GIT_COMMITTER_NAME
unset GIT_COMMITTER_EMAIL

# Clear environment variables
unset OPENCLAW_SESSION_KEY
unset OPENCLAW_CHANNEL_ID

# Create a dummy PRD and required structure
mkdir -p docs/PRDs
echo "dummy prd content" > docs/PRDs/dummy.md

# Initialize Git to pass boundary check
source "${PROJECT_ROOT}/scripts/e2e/setup_sandbox.sh"
init_git_test_sandbox "$(pwd)"

# Apply SDLC infrastructure
"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1

echo "test_output.log" >> .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo ".tmp" >> .gitignore
git add docs/PRDs/dummy.md .gitignore STATE.md preflight.sh
git commit -m "init" > /dev/null

if ! git rev-parse --verify HEAD > /dev/null 2>&1; then
    echo "❌ test_missing_channel.sh FAILED: Sandbox git bootstrap did not produce an initial commit."
    exit 1
fi

# Run orchestrator WITHOUT the --channel parameter
export PYTHONPATH="${PROJECT_ROOT}/scripts:$PYTHONPATH"
export SDLC_BYPASS_BRANCH_CHECK=1
set +e
env -u SDLC_TEST_MODE "$DEV_PYTHON" "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --max-prs-to-process 1 --coder-session-strategy always --force-replan true > test_output.log 2>&1
EXIT_CODE=$?
set -e

cat test_output.log

if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ test_missing_channel.sh FAILED: Orchestrator unexpectedly succeeded without channel parameter."
    exit 1
fi

if ! grep -q "\[FATAL_STARTUP\]" test_output.log; then
    echo "❌ test_missing_channel.sh FAILED: Output missing [FATAL_STARTUP] string."
    exit 1
fi

if ! grep -q "Missing channel parameter" test_output.log; then
    echo "❌ test_missing_channel.sh FAILED: Output missing detailed error message."
    exit 1
fi

echo "✅ test_missing_channel.sh PASSED"
rm -rf "$SANDBOX_DIR"
exit 0
