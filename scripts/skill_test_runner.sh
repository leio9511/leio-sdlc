#!/bin/bash
# ==========================================
# skill_test_runner.sh
# Implements PRD_010 Section 3.4 (Skill Test Runner Protocol)
# ==========================================

set -o pipefail

usage() {
    cat <<'EOF'
Usage:
  scripts/skill_test_runner.sh <SKILL_PATH> [TEST_PROMPT]
  scripts/skill_test_runner.sh --runtime-smoke [--runtime-python PYTHON] <SKILL_PATH>

Runtime smoke policy:
  Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation.
EOF
}

MODE="agent"
RUNTIME_PYTHON_OVERRIDE=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --runtime-smoke)
            MODE="runtime-smoke"
            shift
            ;;
        --runtime-python)
            if [ -z "${2:-}" ]; then
                echo "[skill_test_runner] ❌ Missing value for --runtime-python" >&2
                usage >&2
                exit 2
            fi
            RUNTIME_PYTHON_OVERRIDE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -* )
            echo "[skill_test_runner] ❌ Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            break
            ;;
    esac
done

SKILL_PATH="${1:-}"
TEST_PROMPT="${2:-READY?}"

if [ -z "$SKILL_PATH" ]; then
    usage >&2
    exit 1
fi

if [ "$MODE" = "runtime-smoke" ]; then
    if [ -n "$RUNTIME_PYTHON_OVERRIDE" ]; then
        RUNTIME_PYTHON="$RUNTIME_PYTHON_OVERRIDE"
    else
        RUNTIME_PYTHON="$SKILL_PATH/.venv/bin/python"
    fi

    SMOKE_SCRIPT="$SKILL_PATH/scripts/runtime_smoke.py"

    if [ ! -x "$RUNTIME_PYTHON" ]; then
        echo "[skill_test_runner] ❌ Missing explicit runtime interpreter: $RUNTIME_PYTHON" >&2
        echo "[skill_test_runner] Runtime smoke mode requires <SKILL_PATH>/.venv/bin/python or --runtime-python PYTHON; it will not use ambient python3 or create the runtime .venv." >&2
        exit 1
    fi

    if [ ! -f "$SMOKE_SCRIPT" ]; then
        echo "[skill_test_runner] ❌ Missing official runtime smoke script: $SMOKE_SCRIPT" >&2
        exit 1
    fi

    echo "=================================================="
    echo "[skill_test_runner] 🚀 Running official runtime smoke..."
    echo "[skill_test_runner] 📂 Target Skill: $SKILL_PATH"
    echo "[skill_test_runner] 🐍 Runtime Python: $RUNTIME_PYTHON"
    echo "[skill_test_runner] 💨 Smoke Script: $SMOKE_SCRIPT"
    echo "=================================================="

    "$RUNTIME_PYTHON" "$SMOKE_SCRIPT" \
        --skill-root "$SKILL_PATH" \
        --expected-runtime-python "$RUNTIME_PYTHON"
    exit $?
fi

# Generate a unique validation token to prevent false positives from prompt echoing
V_TOKEN="$(date +%s)_$RANDOM"

echo "=================================================="
echo "[skill_test_runner] 🚀 Spawning sub-agent test runner..."
echo "[skill_test_runner] 📂 Target Skill: $SKILL_PATH"
echo "[skill_test_runner] 💬 Test Prompt: $TEST_PROMPT"
echo "[skill_test_runner] 🔑 Validation Token: $V_TOKEN"
echo "=================================================="

SESSION_ID="test-runner-$(date +%s)-$RANDOM"

META_PROMPT="You are an autonomous QA Test Runner sub-agent.
Your strict protocol:
1. Locate and read the skill documentation at: $SKILL_PATH/SKILL.md to understand its behavior.
2. Execute the user's test prompt: '$TEST_PROMPT' using whatever tools the skill provides.
3. Critically evaluate if the test prompt was successfully executed according to the skill's defined purpose.
4. MANDATORY: If the execution was successful and valid, you MUST output the exact string 'PASSED_' concatenated with the validation token '$V_TOKEN' (e.g., if token is 123, output PASSED_123) on a new line at the very end of your final response. If it fails or errors, output 'FAILED_' concatenated with the token.
Begin execution now."

TMP_LOG=$(mktemp)
openclaw agent --session-id "$SESSION_ID" -m "$META_PROMPT" | tee "$TMP_LOG"

RUN_STATUS=${PIPESTATUS[0]}
if [ "$RUN_STATUS" -ne 0 ]; then
    echo "[skill_test_runner] ❌ FAILURE: openclaw agent exited with status $RUN_STATUS."
    rm -f "$TMP_LOG"
    exit "$RUN_STATUS"
fi

echo ""
echo "=================================================="
echo "[skill_test_runner] 📊 Evaluation Phase"

# Since the prompt explains concatenation, the exact string PASSED_$V_TOKEN will only exist if the agent generated it.
if grep -q "PASSED_$V_TOKEN" "$TMP_LOG"; then
    echo "[skill_test_runner] ✅ SUCCESS: Valid verification token (PASSED_$V_TOKEN) detected."
    rm -f "$TMP_LOG"
    exit 0
else
    echo "[skill_test_runner] ❌ FAILURE: Verification token not found or test failed."
    rm -f "$TMP_LOG"
    exit 1
fi
