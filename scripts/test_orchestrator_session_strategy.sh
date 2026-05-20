#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
echo "Running Orchestrator Session Strategy Tests..."
"$DEV_PYTHON" tests/test_orchestrator_session_strategy.py
echo "Session Strategy Tests passed."
