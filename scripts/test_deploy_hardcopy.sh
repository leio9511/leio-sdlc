#!/bin/bash
set -e

echo "=== Running Hard-Copy Deploy & Rollback Integration Test ==="

# 1. Define a mock HOME directory
MOCK_HOME="/tmp/mock_home_$$"
export HOME_MOCK="$MOCK_HOME"

# Clean up any previous run
rm -rf "$MOCK_HOME"

SKILL_NAME="test-skill"
MOCK_SKILL_SRC="$MOCK_HOME/src/$SKILL_NAME"
MOCK_SKILLS_DIR="$MOCK_HOME/.openclaw/skills"
MOCK_RELEASES_DIR="$MOCK_HOME/.openclaw/.releases/$SKILL_NAME"

# 2. Create dummy skills directory and src
mkdir -p "$MOCK_SKILL_SRC"

# Create dummy content
echo "v1" > "$MOCK_SKILL_SRC/version.txt"

# Provide deploy and rollback scripts
cp "$PWD/deploy.sh" "$MOCK_SKILL_SRC/deploy.sh"
cp "$PWD/scripts/rollback.sh" "$MOCK_SKILL_SRC/rollback.sh"
chmod +x "$MOCK_SKILL_SRC/deploy.sh" "$MOCK_SKILL_SRC/rollback.sh"

cd "$MOCK_SKILL_SRC"

echo "--- test_deploy_skips_gemini_link_when_absent ---"
# Ensure gemini is NOT in PATH
# We create a fake PATH without the directory that contains gemini
REAL_GEMINI=$(command -v gemini || true)
if [ -n "$REAL_GEMINI" ]; then
    GEMINI_DIR=$(dirname "$REAL_GEMINI")
    export PATH=$(echo $PATH | sed "s|:$GEMINI_DIR||g" | sed "s|^$GEMINI_DIR:||g")
fi

./deploy.sh > deploy_no_gemini.log 2>&1
if grep -q "gemini skills link" deploy_no_gemini.log; then
    echo "❌ Assertion Failed: Executed gemini link when absent!"
    exit 1
fi
echo "✅ Passed: Skipped link logic when absent."

echo "--- test_deploy_executes_gemini_link_when_present ---"
# Mock the gemini command
mkdir -p "/tmp/mock_bin"
cat << 'MOCK' > "/tmp/mock_bin/gemini"
#!/bin/bash
echo "Mock gemini executed with args: $@"
MOCK
chmod +x "/tmp/mock_bin/gemini"

export PATH="/tmp/mock_bin:$PATH"

sleep 1
echo "v2" > "version.txt"
./deploy.sh > deploy_with_gemini.log 2>&1

if ! grep -q "Gemini CLI detected" deploy_with_gemini.log; then
    echo "❌ Assertion Failed: Did not detect gemini CLI!"
    exit 1
fi

if ! grep -q "Mock gemini executed with args: skills link" deploy_with_gemini.log; then
    echo "❌ Assertion Failed: Did not execute gemini link when present!"
    cat deploy_with_gemini.log
    exit 1
fi
echo "✅ Passed: Executed link logic when present."

# Clean up mock bin
rm -rf "/tmp/mock_bin"

# Test Rollback
./rollback.sh > /dev/null 2>&1

if [ "$(cat "$MOCK_SKILLS_DIR/$SKILL_NAME/version.txt")" != "v1" ]; then
    echo "❌ Assertion Failed: Rollback failed. Expected v1 but got $(cat "$MOCK_SKILLS_DIR/$SKILL_NAME/version.txt")"
    exit 1
fi

# Clean up
rm -rf "$MOCK_HOME"

echo "✅ Hard-Copy Deploy & Rollback Integration Test PASSED"
