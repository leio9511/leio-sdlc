#!/bin/bash
set -e

# test_agent_driver_gemini.sh
# Standalone E2E test harness for Gemini driver integration
# Usage: ./test_agent_driver_gemini.sh [model_name]
# Defaults to gemini-2.5-flash if not provided.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

export LLM_DRIVER="gemini"
export TEST_MODEL="${1:-${TEST_MODEL:-gemini-2.5-flash}}"
export SDLC_MOCK_LLM_RESPONSE="OK mocked response"

echo "==========================================="
echo "Running Isolated E2E Test for Gemini Driver"
echo "Model: $TEST_MODEL"
echo "==========================================="

# Create a temporary test workspace
TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"
init_hermetic_sandbox "$TEST_DIR/scripts"

# Create a minimal test script
cat << PYEOF > test_gemini.py
import sys
import os
sys.path.insert(0, "$PROJECT_ROOT/scripts")

try:
    from agent_driver import invoke_agent
except ImportError as e:
    print(f"Failed to import agent_driver: {e}")
    sys.exit(1)

task = "Respond with a simple 'OK' if you receive this message. This is a connectivity test."
print("Testing Gemini driver invocation...")

try:
    session = invoke_agent(task, role="test_harness")
    if session:
        print("Test successful, session created.")
    else:
        print("Test failed, no session created.")
        sys.exit(1)
except Exception as e:
    print(f"Test failed with exception: {e}")
    sys.exit(1)
PYEOF

python3 test_gemini.py
RESULT=$?

rm -rf "$TEST_DIR"

if [ $RESULT -eq 0 ]; then
    echo "==========================================="
    echo "✅ Isolated E2E Test Passed"
    echo "==========================================="
    exit 0
else
    echo "==========================================="
    echo "❌ Isolated E2E Test Failed"
    echo "==========================================="
    exit 1
fi
