#!/bin/bash
set -e

# Setup sandbox
SANDBOX_DIR=$(mktemp -d -t dual_deploy_sandbox_XXXXXX)
export HOME_MOCK="$SANDBOX_DIR"

echo "Running dual deploy test in sandbox: $SANDBOX_DIR"

# Ensure we are in the project root
cd "$(dirname "$0")/.." || exit 1

# Make sure some dummy files exist just in case
mkdir -p scripts
touch scripts/dummy.py
touch scripts/dummy.sh
chmod +x scripts/dummy.sh

# Execute deployment script
./deploy.sh --no-restart

# Verify deployment
DEPLOY_DIR="$HOME_MOCK/.openclaw/skills/leio-sdlc"

if [ ! -d "$DEPLOY_DIR" ]; then
    echo "❌ Deployment directory not found: $DEPLOY_DIR"
    exit 1
fi

if [ ! -d "$DEPLOY_DIR/scripts" ]; then
    echo "❌ scripts directory not found in deployment"
    exit 1
fi

# Verify .py and .sh distribution
PY_FILES=$(find "$DEPLOY_DIR/scripts" -name "*.py" | wc -l)
SH_FILES=$(find "$DEPLOY_DIR/scripts" -name "*.sh" | wc -l)

if [ "$PY_FILES" -eq 0 ]; then
    echo "❌ No .py files deployed"
    exit 1
fi

if [ "$SH_FILES" -eq 0 ]; then
    echo "❌ No .sh files deployed"
    exit 1
fi

# Assert dummy files exist
if [ ! -f "$DEPLOY_DIR/scripts/dummy.py" ]; then
    echo "❌ dummy.py not found in deployed scripts"
    exit 1
fi

if [ ! -f "$DEPLOY_DIR/scripts/dummy.sh" ]; then
    echo "❌ dummy.sh not found in deployed scripts"
    exit 1
fi

# Verify unnecessary test source files are omitted (tests/ directory should not be deployed)
# Actually, wait, .release_ignore ignores tests/ but we should verify it.
if [ -d "$DEPLOY_DIR/tests" ]; then
    echo "❌ tests/ directory was mistakenly deployed!"
    exit 1
fi

# Cleanup
echo "Cleaning up sandbox..."
rm -rf "$SANDBOX_DIR"
rm -f scripts/dummy.py scripts/dummy.sh

echo "✅ Test 034 Dual Deploy passed."
exit 0
