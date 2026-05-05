#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)

PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
TMP_TEST_LOG=$(mktemp)
TMP_BASH_IGNORE=$(mktemp)
TMP_PYTEST_IGNORE=$(mktemp)
IGNORE_MANIFEST="$PROJECT_DIR/ignore_tests.json"
FAIL_CLOSED_STATEMENT="If ignore_tests.json is missing or malformed, preflight must fail closed."
QUARANTINE_GREEN_STATEMENT="A non-empty ignore list may produce debt-quarantine green, which is distinct from true full green."

declare -A IGNORE_BASH=()
declare -a PYTEST_IGNORE_ARGS=()
BASH_IGNORE_COUNT=0
PYTEST_IGNORE_COUNT=0

RUN_LIVE_LLM=0
for arg in "$@"; do
    if [[ "$arg" == "--live-llm" ]]; then
        RUN_LIVE_LLM=1
    fi
done

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

cleanup() {
    rm -f "$TMP_TEST_LOG" "$TMP_BASH_IGNORE" "$TMP_PYTEST_IGNORE"
}
trap cleanup EXIT

fail_ignore_manifest() {
    echo "❌ PREFLIGHT FAILED: $FAIL_CLOSED_STATEMENT"
    exit 1
}

load_ignore_manifest() {
    if [[ ! -f "$IGNORE_MANIFEST" ]]; then
        fail_ignore_manifest
    fi

    if ! python3 - "$IGNORE_MANIFEST" "$TMP_BASH_IGNORE" "$TMP_PYTEST_IGNORE" <<'PY'
import json
import sys

manifest_path, bash_out, pytest_out = sys.argv[1:4]
try:
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not isinstance(manifest, dict):
        raise ValueError("top-level value must be an object")

    allowed_keys = {"bash", "pytest"}
    unknown_keys = sorted(set(manifest) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"unknown top-level keys: {', '.join(unknown_keys)}")

    for key in ("bash", "pytest"):
        value = manifest.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise ValueError(f"{key}[{index}] must be a string")
            if "\n" in item:
                raise ValueError(f"{key}[{index}] must not contain newlines")

    with open(bash_out, "w", encoding="utf-8") as f:
        for item in manifest.get("bash", []):
            f.write(item + "\n")

    with open(pytest_out, "w", encoding="utf-8") as f:
        for item in manifest.get("pytest", []):
            f.write(item + "\n")
except Exception as exc:
    print(f"ignore_tests.json error: {exc}", file=sys.stderr)
    sys.exit(1)
PY
    then
        fail_ignore_manifest
    fi

    while IFS= read -r ignored_path || [[ -n "$ignored_path" ]]; do
        if [[ -n "$ignored_path" ]]; then
            IGNORE_BASH["$ignored_path"]=1
            ((BASH_IGNORE_COUNT++))
        fi
    done < "$TMP_BASH_IGNORE"

    while IFS= read -r ignored_path || [[ -n "$ignored_path" ]]; do
        if [[ -n "$ignored_path" ]]; then
            PYTEST_IGNORE_ARGS+=("--ignore=$ignored_path")
            ((PYTEST_IGNORE_COUNT++))
        fi
    done < "$TMP_PYTEST_IGNORE"
}

TOTAL_PASSED=0

report_test_failure() {
    local desc="$1"
    echo "❌ PREFLIGHT FAILED: $desc"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$TMP_TEST_LOG" | head -n 50; then
        :
    else
        tail -n 50 "$TMP_TEST_LOG"
    fi
    echo "==============================================================="
    exit 1
}

run_test() {
    local cmd="$1"
    local desc="$2"
    
    if ! eval "$cmd" > "$TMP_TEST_LOG" 2>&1; then
        report_test_failure "$desc"
    fi
    ((TOTAL_PASSED++))
}

run_test_argv() {
    local desc="$1"
    shift

    if ! "$@" > "$TMP_TEST_LOG" 2>&1; then
        report_test_failure "$desc"
    fi
    ((TOTAL_PASSED++))
}

run_live_llm_test() {
    local cmd="$1"
    local desc="$2"
    
    if ! eval "$cmd" > "$TMP_TEST_LOG" 2>&1; then
        echo "[E2E WARNING] $desc failed. Continuing."
        echo "=== WARNING DETAILS ==="
        if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$TMP_TEST_LOG" | head -n 50; then
            :
        else
            tail -n 50 "$TMP_TEST_LOG"
        fi
        echo "======================="
    else
        ((TOTAL_PASSED++))
    fi
}

load_ignore_manifest

# ISSUE-1088: Prune legacy test sandboxes
rm -rf tests/planner_sandbox_* tests/manager_sandbox_* 2>/dev/null || true

shopt -s nullglob

# 0. Structural Gates
run_test "pytest tests/test_template_compliance.py" "Template Compliance Gate"

# 1. Bash Tests Discovery
for f in scripts/test_*.sh; do
    if [[ -n "${IGNORE_BASH[$f]:-}" ]]; then
        continue
    fi
    run_test "bash $f" "Bash Test: $f"
done

# 2. Python Tests Discovery
if [ -d "tests" ]; then
    run_test_argv "Pytest functional & unittest suite" pytest tests/ "${PYTEST_IGNORE_ARGS[@]}"
fi

for f in scripts/test_*.py; do
    run_test "python3 $f" "Python Test: $f"
done

# 3. Node.js Tests Discovery
if [ -f "package.json" ] && grep -q '"test"' package.json; then
    run_test "npm test" "NPM Test"
else
    for f in scripts/test_*.js; do
        run_test "node $f" "Node.js Test: $f"
    done
fi

# 4. E2E Mocked Tests
for f in scripts/e2e/mocked/*.sh; do
    run_test "bash $f" "Mocked E2E: $(basename "$f")"
done

# 5. E2E Live LLM Tests
if [ $RUN_LIVE_LLM -eq 1 ]; then
    for f in scripts/e2e/live_llm/*.sh; do
        run_live_llm_test "bash $f" "Live LLM E2E: $(basename "$f")"
    done
fi

# Offline Syntax Checks
if [ -f "scripts/agent_driver.py" ]; then
    run_test "python3 -m py_compile scripts/agent_driver.py" "Syntax Check: agent_driver.py"
fi

if (( BASH_IGNORE_COUNT + PYTEST_IGNORE_COUNT > 0 )); then
    echo "⚠️ $QUARANTINE_GREEN_STATEMENT"
    echo "⚠️ Debt quarantine ignored $BASH_IGNORE_COUNT bash target(s) and $PYTEST_IGNORE_COUNT pytest target(s)."
fi

echo "✅ $TOTAL_PASSED tests/test-suites passed."
exit 0
