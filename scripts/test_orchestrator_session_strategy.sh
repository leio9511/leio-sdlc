#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Running Orchestrator Session Strategy Tests..."
"$PROJECT_ROOT/scripts/dev_python.sh" tests/test_orchestrator_session_strategy.py
echo "Session Strategy Tests passed."
