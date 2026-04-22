#!/bin/bash
set -e

PROJECT_ROOT="$(pwd)"

echo "Running live-LLM validation harness for Coder revision loop..."

# Test should not be a hard gate. If SDLC_LIVE_TEST_MODE is not set, skip it gracefully.
if [ "$SDLC_LIVE_TEST_MODE" != "true" ]; then
    echo "SDLC_LIVE_TEST_MODE is not true. Skipping live LLM validation gracefully."
    exit 0
fi

if [ -z "$GEMINI_API_KEY" ] && [ -z "$OPENCLAW_API_KEY" ]; then
    echo "No API key found. Skipping live LLM validation gracefully."
    exit 0
fi

# Mock environment setup
MOCK_WORKSPACE="/tmp/mock_sdlc_live_workspace_$$"
mkdir -p "$MOCK_WORKSPACE"
cd "$MOCK_WORKSPACE"

cat << 'PROMPT' > run_live.py
import sys
import os

# Add scripts to path
sys.path.insert(0, os.path.abspath('scripts'))

from agent_driver import invoke_agent, build_prompt

def main():
    # Construct the revision prompt using the hardened contract
    feedback_content = "Reviewer says: The function `calculate_total` is missing a return statement."
    prompt = build_prompt("coder_revision", feedback_content=feedback_content)
    
    # We add a dummy task context to give the model something to work with
    task_string = (
        "You are working on a python project. Here is your PR contract:\n"
        "Implement `calculate_total` in `math_utils.py`.\n"
        "Here is the revision feedback:\n" + prompt
    )
    
    print("Invoking agent with hardened revision prompt...")
    # Invoke the agent. It will use gemini or openclaw based on env vars
    result = invoke_agent(task_string, role="coder", run_dir=".")
    
    if result is None:
        print("Agent invocation failed.")
        sys.exit(1)
        
    response_text = result.stdout.lower()
    print("LLM Response:\n", response_text)
    
    # We check if it is purely an acknowledgment. It shouldn't be.
    # It should mention editing a file or creating code.
    ack_phrases = [
        "i have read the instructions",
        "i will fix it",
        "acknowledged",
        "understood"
    ]
    
    is_ack_only = any(phrase in response_text for phrase in ack_phrases) and "def calculate_total" not in response_text and "```python" not in response_text
    
    if is_ack_only:
        print("FAIL: The LLM responded with pure acknowledgment instead of executing the fix.")
        sys.exit(1)
        
    print("PASS: The LLM provided an action-oriented response.")

if __name__ == "__main__":
    main()
PROMPT

# Move to the project root to run the python script so it can import agent_driver properly
cd "$PROJECT_ROOT"

# Unset SDLC_TEST_MODE so we actually hit the real endpoint
export SDLC_TEST_MODE="false"

# Run the live test
python3 "$MOCK_WORKSPACE/run_live.py"

# Cleanup
rm -rf "$MOCK_WORKSPACE"

echo "Live validation completed successfully."
exit 0
