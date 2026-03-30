#!/bin/bash
set -e

echo "Running E2E integration test for agent_driver with Gemini..."
export LLM_DRIVER=gemini
export TEST_MODEL="${TEST_MODEL:-google/gemini-2.0-flash}"

# We just write a simple python script that calls invoke_agent and checks if it works
cat << 'PYEOF' > test_invoke.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))
from agent_driver import invoke_agent

try:
    # A simple task that the model should just reply "ok" or something fast
    # But since gemini is headless, it will print to stdout.
    session_key = invoke_agent("Reply exactly with the word 'PONG'. Nothing else.", role="test")
    if session_key:
        print("Agent invocation succeeded.")
        sys.exit(0)
    else:
        print("Agent invocation returned None.")
        sys.exit(1)
except Exception as e:
    print(f"Agent invocation failed: {e}")
    sys.exit(1)
PYEOF

export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
python3 test_invoke.py
rm -f test_invoke.py
echo "✅ agent_driver Gemini E2E test passed."
