#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)

PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
DEV_PYTHON="$PROJECT_DIR/scripts/dev_python.sh"
if [[ ! -x "$DEV_PYTHON" ]]; then
    echo "❌ PREFLIGHT FAILED: Missing executable controlled Python wrapper: $DEV_PYTHON"
    echo "Formal Python preflight checks must run through the repository-root .venv wrapper."
    exit 1
fi
PYTHON_CMD=("$DEV_PYTHON")
TMP_TEST_LOG=$(mktemp)
TMP_BASH_IGNORE=$(mktemp)
TMP_PYTEST_IGNORE=$(mktemp)
IGNORE_MANIFEST="$PROJECT_DIR/ignore_tests.json"
FAIL_CLOSED_STATEMENT="If ignore_tests.json is missing or malformed, preflight must fail closed."
QUARANTINE_GREEN_STATEMENT="A non-empty ignore list may produce debt-quarantine green, which is distinct from true full green."
FAIL_FAST_MODE_NAME="fail-fast"
REPORT_ALL_MODE_NAME="report-all"

TRAP_MODE=0
if [[ "${SDLC_TEST_MODE:-}" == "trap" ]]; then
    TRAP_MODE=1
fi
TRAP_VENV_DIR=""
PREFLIGHT_BASE_PATH="$PATH"
PREFLIGHT_BASE_VIRTUAL_ENV="${VIRTUAL_ENV:-}"
MODE="$FAIL_FAST_MODE_NAME"
RUN_LIVE_LLM=0
for arg in "$@"; do
    case "$arg" in
        --live-llm)
            RUN_LIVE_LLM=1
            ;;
        --report-all)
            MODE="$REPORT_ALL_MODE_NAME"
            ;;
        --trap-mode)
            TRAP_MODE=1
            ;;
        *)
            echo "❌ PREFLIGHT FAILED: Unknown argument: $arg"
            exit 1
            ;;
    esac
done

declare -A IGNORE_BASH=()
declare -a PYTEST_IGNORE_ARGS=()
declare -a FAILED_CHECKS=()
declare -a BLOCKED_CHECKS=()
BASH_IGNORE_COUNT=0
PYTEST_IGNORE_COUNT=0
TOTAL_PASSED=0
TEMPLATE_COMPLIANCE_FAILED=0

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks ($MODE mode)..."

cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

cleanup() {
    rm -f "$TMP_TEST_LOG" "$TMP_BASH_IGNORE" "$TMP_PYTEST_IGNORE"
    if [[ -n "$TRAP_VENV_DIR" ]]; then
        rm -rf "$TRAP_VENV_DIR"
    fi
}
trap cleanup EXIT

activate_trap_mode() {
    TRAP_VENV_DIR=$(mktemp -d "${TMPDIR:-/tmp}/leio-preflight-trap-venv.XXXXXXXXXX")
    "${PYTHON_CMD[@]}" -m venv "$TRAP_VENV_DIR"
    cat > "$TRAP_VENV_DIR/bin/pytest" <<'SH'
#!/usr/bin/env bash
echo "No module named 'pytest'" >&2
exec "$(dirname "$0")/python" -m pytest "$@"
SH
    chmod +x "$TRAP_VENV_DIR/bin/pytest"
    if [[ -n "${PREFLIGHT_TRAP_VENV_MARKER_FILE:-}" ]]; then
        printf '%s\n' "$TRAP_VENV_DIR" > "$PREFLIGHT_TRAP_VENV_MARKER_FILE"
    fi

    TRAP_BIN_DIR="$TRAP_VENV_DIR/trap_bin"
    mkdir -p "$TRAP_BIN_DIR"
    cp "$PROJECT_DIR/tests/trap_stub_openclaw.sh" "$TRAP_BIN_DIR/openclaw"
    chmod +x "$TRAP_BIN_DIR/openclaw"
}

enter_trap_ambient() {
    if (( TRAP_MODE == 1 )); then
        export PATH="$TRAP_BIN_DIR:$TRAP_VENV_DIR/bin:$PREFLIGHT_BASE_PATH"
        export VIRTUAL_ENV="$TRAP_VENV_DIR"
    fi
}

leave_trap_ambient() {
    if (( TRAP_MODE == 1 )); then
        export PATH="$PREFLIGHT_BASE_PATH"
        if [[ -n "$PREFLIGHT_BASE_VIRTUAL_ENV" ]]; then
            export VIRTUAL_ENV="$PREFLIGHT_BASE_VIRTUAL_ENV"
        else
            unset VIRTUAL_ENV
        fi
    fi
}

if (( TRAP_MODE == 1 )); then
    activate_trap_mode
    enter_trap_ambient
fi

fail_ignore_manifest() {
    echo "❌ PREFLIGHT FAILED: $FAIL_CLOSED_STATEMENT"
    exit 1
}

load_ignore_manifest() {
    if [[ ! -f "$IGNORE_MANIFEST" ]]; then
        fail_ignore_manifest
    fi

    if ! "${PYTHON_CMD[@]}" - "$IGNORE_MANIFEST" "$TMP_BASH_IGNORE" "$TMP_PYTEST_IGNORE" <<'PY'
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

print_log_excerpt() {
    if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$TMP_TEST_LOG" | head -n 50; then
        :
    else
        tail -n 50 "$TMP_TEST_LOG"
    fi
}

report_test_failure() {
    local desc="$1"

    if [[ "$MODE" == "$FAIL_FAST_MODE_NAME" ]]; then
        echo "❌ PREFLIGHT FAILED: $desc"
        echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
        print_log_excerpt
        echo "==============================================================="
        exit 1
    fi

    FAILED_CHECKS+=("$desc")
    echo "❌ CHECK FAILED (continuing due to $REPORT_ALL_MODE_NAME): $desc"
    echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
    print_log_excerpt
    echo "==============================================================="
}

mark_test_blocked() {
    local desc="$1"
    local reason="$2"

    BLOCKED_CHECKS+=("$desc :: $reason")
    echo "⚠️ BLOCKED: $desc ($reason)"
}

run_test() {
    local cmd="$1"
    local desc="$2"

    if ! eval "$cmd" > "$TMP_TEST_LOG" 2>&1; then
        report_test_failure "$desc"
        return 1
    fi
    ((TOTAL_PASSED++))
    return 0
}

run_test_argv() {
    local desc="$1"
    shift

    if ! "$@" > "$TMP_TEST_LOG" 2>&1; then
        report_test_failure "$desc"
        return 1
    fi
    ((TOTAL_PASSED++))
    return 0
}

run_live_llm_test() {
    local cmd="$1"
    local desc="$2"

    if ! eval "$cmd" > "$TMP_TEST_LOG" 2>&1; then
        echo "[E2E WARNING] $desc failed. Continuing."
        echo "=== WARNING DETAILS ==="
        print_log_excerpt
        echo "======================="
    else
        ((TOTAL_PASSED++))
    fi
}

finalize_preflight() {
    if (( BASH_IGNORE_COUNT + PYTEST_IGNORE_COUNT > 0 )); then
        if (( TRAP_MODE == 1 )); then
            echo "TRAP REMEDIATION PENDING"
            echo "This preflight run is green only under the temporary existing ignore-manifest rollout for trap-mode failures."
            echo "Remaining trap failures must be burned down to zero before this issue is complete."
        else
            echo "⚠️ $QUARANTINE_GREEN_STATEMENT"
            echo "⚠️ Debt quarantine ignored $BASH_IGNORE_COUNT bash target(s) and $PYTEST_IGNORE_COUNT pytest target(s)."
        fi
    fi

    if (( ${#FAILED_CHECKS[@]} > 0 )); then
        echo "❌ PREFLIGHT FAILED: ${#FAILED_CHECKS[@]} check(s) failed in $REPORT_ALL_MODE_NAME mode."
        echo "=== FINAL FAILURE SUMMARY ($REPORT_ALL_MODE_NAME) ==="
        local idx=1
        for desc in "${FAILED_CHECKS[@]}"; do
            echo "$idx. $desc"
            ((idx++))
        done

        if (( ${#BLOCKED_CHECKS[@]} > 0 )); then
            echo "=== BLOCKED / NOT RUN ==="
            idx=1
            for blocked in "${BLOCKED_CHECKS[@]}"; do
                echo "$idx. $blocked"
                ((idx++))
            done
        fi

        echo "==============================================="
        exit 1
    fi

    if (( TRAP_MODE == 1 && BASH_IGNORE_COUNT + PYTEST_IGNORE_COUNT == 0 )); then
        echo "TRAP MODE CLEAN"
        echo "Trap-mode preflight passed with no remaining trap remediation entries."
    fi

    echo "✅ $TOTAL_PASSED tests/test-suites passed."
    exit 0
}

load_ignore_manifest

# ISSUE-1088: Prune legacy test sandboxes
rm -rf tests/planner_sandbox_* tests/manager_sandbox_* 2>/dev/null || true

shopt -s nullglob

# 0. Structural Gates
if ! run_test_argv "Template Compliance Gate" "${PYTHON_CMD[@]}" -m pytest tests/test_template_compliance.py; then
    TEMPLATE_COMPLIANCE_FAILED=1
fi

# 1. Bash Tests Discovery
for f in scripts/test_*.sh; do
    if [[ -n "${IGNORE_BASH[$f]:-}" ]]; then
        continue
    fi
    run_test "bash $f" "Bash Test: $f"
done

# 2. Python Tests Discovery
if [ -d "tests" ]; then
    if [[ "$MODE" == "$REPORT_ALL_MODE_NAME" && $TEMPLATE_COMPLIANCE_FAILED -eq 1 ]]; then
        mark_test_blocked "Pytest functional & unittest suite" "Template Compliance Gate failed earlier; broader pytest suite would only duplicate non-actionable structural failures"
    else
        run_test_argv "Pytest functional & unittest suite" "${PYTHON_CMD[@]}" -m pytest tests/ "${PYTEST_IGNORE_ARGS[@]}"
    fi
fi

for f in scripts/test_*.py; do
    run_test_argv "Python Test: $f" "${PYTHON_CMD[@]}" "$f"
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
    if [[ -n "${IGNORE_BASH[$f]:-}" ]]; then
        continue
    fi
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
    run_test_argv "Syntax Check: agent_driver.py" "${PYTHON_CMD[@]}" -m py_compile scripts/agent_driver.py
fi

finalize_preflight
