import os
import subprocess
import sys

# Set env vars to mock openclaw
os.environ["LLM_DRIVER"] = "openclaw"
os.environ["PATH"] = f"{os.path.abspath('mock_bin')}:{os.environ['PATH']}"
os.environ["HOME_MOCK"] = os.path.abspath(".tmp_home_mock")
os.makedirs("mock_bin", exist_ok=True)
os.makedirs(".tmp_home_mock", exist_ok=True)

# Create a mock openclaw binary
with open("mock_bin/openclaw", "w") as f:
    f.write('''#!/bin/bash
if [ "$1" == "agents" ] && [ "$2" == "list" ]; then
    echo "No agents"
    exit 0
elif [ "$1" == "agents" ] && [ "$2" == "add" ]; then
    echo "Created agent"
    exit 0
elif [ "$1" == "agent" ]; then
    echo "Agent ran"
    exit 0
else
    echo "Unknown"
    exit 1
fi
''')
os.chmod("mock_bin/openclaw", 0o755)

sys.path.insert(0, os.path.abspath("scripts"))
from agent_driver import invoke_agent

result = invoke_agent("Hello", session_key="test_key_123")
print("RESULT:", result.stdout.strip())
