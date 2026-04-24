#!/bin/bash
set -e

TARGET_MODEL="${SDLC_MODEL:-gpt}"
TARGET_AGENT="sdlc-generic-openclaw-${TARGET_MODEL//[^a-zA-Z0-9]/-}"
TARGET_AGENT="$(echo "$TARGET_AGENT" | tr '[:upper:]' '[:lower:]' | sed 's/--*/-/g; s/-$//')"
export TARGET_MODEL
export TARGET_AGENT

echo "================================================="
echo "Testing: OpenClaw Isolation Probe"
echo "================================================="

export HOME_MOCK=$(mktemp -d)
WORK_DIR=$(mktemp -d)

cleanup() {
    rm -rf "$HOME_MOCK"
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

mkdir -p "$HOME_MOCK/.openclaw/workspace"
echo "I AM CONTAMINATED" > "$HOME_MOCK/.openclaw/workspace/SOUL.md"

cp -r "$(cd "$(dirname "$0")/.." && pwd)"/* "$WORK_DIR/"
cd "$WORK_DIR"

# Provide a mock openclaw that prints the contents of its agent workspace SOUL.md
mkdir -p mock_bin
cat << 'MOCK' > mock_bin/openclaw
#!/bin/bash
if [ "$1" == "agents" ] && [ "$2" == "list" ]; then
    echo "No agents"
    exit 0
elif [ "$1" == "agents" ] && [ "$2" == "add" ]; then
    echo "Created agent"
    exit 0
elif [ "$1" == "agent" ]; then
    if [ -f "$HOME_MOCK/.openclaw/agents/$TARGET_AGENT/workspace/SOUL.md" ]; then
        cat "$HOME_MOCK/.openclaw/agents/$TARGET_AGENT/workspace/SOUL.md"
    else
        echo "MISSING_SOUL"
    fi
    exit 0
else
    echo "Unknown command: $*"
    exit 1
fi
MOCK
chmod +x mock_bin/openclaw
export PATH="$WORK_DIR/mock_bin:$PATH"

export LLM_DRIVER="openclaw"
export SDLC_MODEL="$TARGET_MODEL"
export SDLC_TEST_MODE="false"
unset SDLC_MOCK_LLM_RESPONSE

mkdir -p "$WORK_DIR/docs/PRDs"
echo "Test PR" > "$WORK_DIR/docs/PRDs/dummy.md"
echo "Test PR" > "$WORK_DIR/dummy_pr.md"

probe_isolation_from_main_workspace() {
    echo "Running probe_isolation_from_main_workspace..."
    OUTPUT=$(python3 scripts/spawn_coder.py --enable-exec-from-workspace --pr-file dummy_pr.md --prd-file docs/PRDs/dummy.md --workdir . --run-dir .)

    if echo "$OUTPUT" | grep -q "I AM CONTAMINATED"; then
        echo "❌ Probe Failed: Execution context is contaminated by main workspace."
        exit 1
    fi

    if ! echo "$OUTPUT" | grep -q "You are a generic execution agent"; then
        echo "❌ Probe Failed: Did not read from isolated workspace. Output: $OUTPUT"
        exit 1
    fi

    echo "✅ Probe Passed: Execution context cleanly isolated."
}

probe_isolation_from_main_workspace
exit 0
