#!/bin/bash
# test_gemini_deploy.sh - Validate gemini-deploy.sh script
set -e

REPO_ROOT="/root/.openclaw/workspace/projects/leio-sdlc"
TEST_DIR=$(mktemp -d)
DEPLOY_SCRIPT="$REPO_ROOT/scripts/gemini-deploy.sh"

echo "🧪 Running Gemini Deploy Test..."
echo "📂 Temp Deployment Directory: $TEST_DIR"

# 1. Run the deployment script
bash "$DEPLOY_SCRIPT" "$TEST_DIR"

# 2. Check Case 1: test_gemini_deploy_creates_files
echo "🔍 Checking created files..."
if [ ! -d "$TEST_DIR/leio-sdlc" ]; then
    echo "❌ Error: leio-sdlc directory not found!"
    exit 1
fi

if [ ! -d "$TEST_DIR/skills/pm-skill" ]; then
    echo "❌ Error: skills/pm-skill directory not found!"
    exit 1
fi

# 3. Check Case 2: test_gemini_deploy_env_template
echo "🔍 Checking .sdlc_env template..."
ENV_FILE="$TEST_DIR/.sdlc_env"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: .sdlc_env file not found!"
    exit 1
fi

if ! grep -q "GEMINI_API_KEY" "$ENV_FILE"; then
    echo "❌ Error: .sdlc_env does not contain GEMINI_API_KEY!"
    exit 1
fi

if ! grep -q "SDLC_MODEL" "$ENV_FILE"; then
    echo "❌ Error: .sdlc_env does not contain SDLC_MODEL!"
    exit 1
fi

# 4. Success
echo "✅ All deployment tests passed!"

# Clean up
rm -rf "$TEST_DIR"
