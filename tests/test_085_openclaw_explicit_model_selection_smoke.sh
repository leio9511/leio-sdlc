#!/bin/bash
set -euo pipefail

normalize_agent_id() {
    local model="$1"
    local normalized
    normalized="$(echo "$model" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/--*/-/g; s/^-//; s/-$//')"
    echo "sdlc-generic-openclaw-$normalized"
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local message="$3"
    if ! echo "$haystack" | grep -q "$needle"; then
        echo "❌ $message"
        echo "--- output start ---"
        echo "$haystack"
        echo "--- output end ---"
        exit 1
    fi
}

assert_not_contains() {
    local haystack="$1"
    local needle="$2"
    local message="$3"
    if echo "$haystack" | grep -q "$needle"; then
        echo "❌ $message"
        echo "--- output start ---"
        echo "$haystack"
        echo "--- output end ---"
        exit 1
    fi
}

echo "================================================="
echo "Testing: OpenClaw Explicit Model Selection Smoke"
echo "================================================="

export HOME_MOCK=$(mktemp -d)
WORK_DIR=$(mktemp -d)
STATE_DIR=$(mktemp -d)
export STATE_DIR
export MAIN_WORKSPACE_SOUL="I AM CONTAMINATED"

cleanup() {
    rm -rf "$HOME_MOCK" "$WORK_DIR" "$STATE_DIR"
}
trap cleanup EXIT

mkdir -p "$HOME_MOCK/.openclaw/workspace"
echo "$MAIN_WORKSPACE_SOUL" > "$HOME_MOCK/.openclaw/workspace/SOUL.md"

cp -r "$(cd "$(dirname "$0")/.." && pwd)"/* "$WORK_DIR/"
cd "$WORK_DIR"

mkdir -p mock_bin
cat <<'MOCK' > mock_bin/openclaw
#!/bin/bash
set -euo pipefail

normalize_agent_id() {
    local model="$1"
    local normalized
    normalized="$(echo "$model" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/--*/-/g; s/^-//; s/-$//')"
    echo "sdlc-generic-openclaw-$normalized"
}

AGENTS_FILE="$STATE_DIR/agents.tsv"
mkdir -p "$STATE_DIR"
touch "$AGENTS_FILE"

if [ "$1" = "agents" ] && [ "$2" = "list" ]; then
    if [ ! -s "$AGENTS_FILE" ]; then
        echo "No agents"
        exit 0
    fi
    cut -f1 "$AGENTS_FILE"
    exit 0
fi

if [ "$1" = "agents" ] && [ "$2" = "show" ]; then
    agent_id="$3"
    line=$(grep -F "${agent_id}"	 "$AGENTS_FILE" || true)
    if [ -z "$line" ]; then
        exit 0
    fi
    model=$(printf '%s' "$line" | cut -f2)
    echo "Model: $model"
    exit 0
fi

if [ "$1" = "agents" ] && [ "$2" = "add" ]; then
    agent_id="$3"
    shift 3
    model=""
    workspace=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --model)
                model="$2"
                shift 2
                ;;
            --workspace)
                workspace="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    printf '%s\t%s\t%s\n' "$agent_id" "$model" "$workspace" >> "$AGENTS_FILE"
    echo "Created agent $agent_id with model $model"
    exit 0
fi

if [ "$1" = "agent" ]; then
    agent_id=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --agent)
                agent_id="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    line=$(grep -F "${agent_id}"	 "$AGENTS_FILE" || true)
    workspace=$(printf '%s' "$line" | cut -f3)
    echo "AGENT_ID:$agent_id"
    if [ -n "$workspace" ] && [ -f "$workspace/SOUL.md" ]; then
        cat "$workspace/SOUL.md"
    else
        echo "MISSING_SOUL"
    fi
    exit 0
fi

echo "Unknown command: $*"
exit 1
MOCK
chmod +x mock_bin/openclaw
export PATH="$WORK_DIR/mock_bin:$PATH"

export LLM_DRIVER="openclaw"
export SDLC_TEST_MODE="false"
unset SDLC_MOCK_LLM_RESPONSE

mkdir -p "$WORK_DIR/docs/PRDs"
echo "Test PR" > "$WORK_DIR/docs/PRDs/dummy.md"
echo "Test PR" > "$WORK_DIR/dummy_pr.md"

run_spawn() {
    local model="$1"
    export SDLC_MODEL="$model"
    python3 scripts/spawn_coder.py --enable-exec-from-workspace --pr-file dummy_pr.md --prd-file docs/PRDs/dummy.md --workdir . --run-dir .
}

first_run_creates_model_specific_agent() {
    local model="gpt"
    local agent_id
    agent_id="$(normalize_agent_id "$model")"
    echo "Running first_run_creates_model_specific_agent..."
    output="$(run_spawn "$model")"
    assert_contains "$output" "AGENT_ID:$agent_id" "Expected first run to execute through $agent_id"
    assert_contains "$output" "You are a generic execution agent" "Expected isolated workspace soul for first run"
    assert_not_contains "$output" "$MAIN_WORKSPACE_SOUL" "First run leaked main workspace context"
    assert_contains "$(cat "$STATE_DIR/agents.tsv")" "$agent_id" "Expected first run to persist $agent_id"
    assert_contains "$(cat "$STATE_DIR/agents.tsv")" $'gpt' "Expected first run to store requested model gpt"
}

same_model_reuses_existing_agent() {
    local model="gpt"
    local agent_id
    agent_id="$(normalize_agent_id "$model")"
    echo "Running same_model_reuses_existing_agent..."
    before_count="$(wc -l < "$STATE_DIR/agents.tsv")"
    output="$(run_spawn "$model")"
    after_count="$(wc -l < "$STATE_DIR/agents.tsv")"
    assert_contains "$output" "AGENT_ID:$agent_id" "Expected repeated run to execute through existing $agent_id"
    if [ "$before_count" -ne "$after_count" ]; then
        echo "❌ Expected same-model run to reuse existing agent without creating a new one"
        exit 1
    fi
}

different_model_resolves_distinct_agent() {
    local model="gemini-3.1-pro-preview"
    local agent_id
    agent_id="$(normalize_agent_id "$model")"
    echo "Running different_model_resolves_distinct_agent..."
    output="$(run_spawn "$model")"
    assert_contains "$output" "AGENT_ID:$agent_id" "Expected different-model run to execute through $agent_id"
    assert_contains "$output" "You are a generic execution agent" "Expected isolated workspace soul for different-model run"
    assert_not_contains "$output" "$MAIN_WORKSPACE_SOUL" "Different-model run leaked main workspace context"
    assert_contains "$(cat "$STATE_DIR/agents.tsv")" "$agent_id" "Expected distinct model-specific agent to be persisted"
    line_count="$(wc -l < "$STATE_DIR/agents.tsv")"
    if [ "$line_count" -lt 2 ]; then
        echo "❌ Expected at least two model-specific agents after switching models"
        exit 1
    fi
}

first_run_creates_model_specific_agent
same_model_reuses_existing_agent
different_model_resolves_distinct_agent

echo "✅ OpenClaw explicit model selection smoke passed."
exit 0
