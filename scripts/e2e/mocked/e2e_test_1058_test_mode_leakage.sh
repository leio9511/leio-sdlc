#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

# Setup a test git repo
WORK_DIR=$(mktemp -d)
init_git_test_sandbox "$WORK_DIR"
cd "$WORK_DIR"
echo "test" > test.txt
git add test.txt
git commit -m "initial commit" > /dev/null 2>&1

touch dummy_prd.md

# Setup hermetic sandbox
init_hermetic_sandbox "$WORK_DIR/scripts"

# We must ensure setup_logging is there too if needed
cp "$PROJECT_ROOT/scripts/setup_logging.py" "$WORK_DIR/scripts/" 2>/dev/null || true
cp "$PROJECT_ROOT/config/prompts.json" "$WORK_DIR/config/" 2>/dev/null || true
cat > "$WORK_DIR/config/sdlc_config.json" <<INNER_EOF
{
    "YELLOW_RETRY_LIMIT": 3,
    "RED_RETRY_LIMIT": 2,
    "GLOBAL_RUN_DIR": "",
    "ENFORCE_GIT_LOCK": true,
    "max_uat_recovery_attempts": 5,
    "ALLOWED_RUNTIME_ROOTS": [
        "$WORK_DIR/scripts"
    ]
}
INNER_EOF

# Script path
ORCHESTRATOR="$WORK_DIR/scripts/orchestrator.py"

run_sandbox_python() {
    "$WORK_DIR/scripts/dev_python.sh" "$@"
}

export SDLC_TEST_MODE=true
export SDLC_RUNTIME_DIR="$WORK_DIR/scripts"

echo "--- Scenario 1: With --enable-exec-from-workspace (Warning only) ---"
# We run it with --test-sleep so it exits quickly
OUTPUT1=$(run_sandbox_python "$ORCHESTRATOR" --workdir "$WORK_DIR" --prd-file dummy_prd.md --force-replan false --channel test --test-sleep --enable-exec-from-workspace 2>&1 || true)
echo "$OUTPUT1"

if echo "$OUTPUT1" | grep -q "\[WARNING\] Running Orchestrator in TEST MODE with mocked LLMs. Production safety checks are bypassed."; then
    echo "Scenario 1 passed: Warning detected."
else
    echo "Scenario 1 failed: Output:"
    echo "$OUTPUT1"
    exit 1
fi

if echo "$OUTPUT1" | grep -q "Production runtime detected but SDLC_TEST_MODE is enabled"; then
    echo "Scenario 1 failed: Fatal prompt detected when it shouldn't be."
    exit 1
fi

echo "--- Scenario 2: Without --enable-exec-from-workspace (Fatal) ---"
set +e
OUTPUT2=$(run_sandbox_python "$ORCHESTRATOR" --workdir "$WORK_DIR" --prd-file dummy_prd.md --force-replan false --channel test --test-sleep 2>&1)
EXIT_CODE=$?
echo "$OUTPUT2"
set -e

if [ $EXIT_CODE -eq 1 ]; then
    echo "Scenario 2 correctly exited with code 1."
else
    echo "Scenario 2 failed to exit with code 1. Exit code: $EXIT_CODE"
    exit 1
fi

if echo "$OUTPUT2" | grep -q "Production runtime detected but SDLC_TEST_MODE is enabled"; then
    echo "Scenario 2 passed: Fatal prompt detected."
else
    echo "Scenario 2 failed: Fatal prompt missing. Output:"
    echo "$OUTPUT2"
    exit 1
fi

# Clean up
rm -rf "$WORK_DIR"

echo "All tests passed successfully."
