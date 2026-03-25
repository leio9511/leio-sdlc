#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
echo "Sandbox: $SANDBOX_DIR"

cd "$SANDBOX_DIR"
# No git init here

if python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --workdir "$(pwd)" --prd-file prd.md --channel "#test" --global-dir "$(pwd)" 2>&1 | grep -q "Git Boundary Enforcement"; then
    echo "✅ test_git_boundary.sh PASSED"
else
    echo "❌ test_git_boundary.sh FAILED: Did not enforce git boundary."
    exit 1
fi
rm -rf "$SANDBOX_DIR"
