#!/bin/bash
set -e

# verify deploy.sh syncs openclaw templates
export HOME_MOCK=$(mktemp -d)
export SDLC_RUNTIME_DIR="$HOME_MOCK/runtime"

mkdir -p "$SDLC_RUNTIME_DIR"

# Mock build_release.sh so we don't actually build .dist? 
# Wait, let's just run it, it's fast.
bash ./deploy.sh --no-restart

# Verify files exist in the deployed directory
PROD_DIR="$SDLC_RUNTIME_DIR/leio-sdlc"

if [ ! -f "$PROD_DIR/TEMPLATES/openclaw_execution_agent/AGENTS.md" ]; then
    echo "❌ AGENTS.md not found in deployed templates"
    exit 1
fi

if [ ! -f "$PROD_DIR/TEMPLATES/openclaw_execution_agent/SOUL.md" ]; then
    echo "❌ SOUL.md not found in deployed templates"
    exit 1
fi

echo "✅ verify deploy.sh syncs openclaw templates passed."
rm -rf "$HOME_MOCK"
exit 0
