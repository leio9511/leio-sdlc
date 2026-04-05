#!/bin/bash
# ==========================================
# STANDARD AGENTIC PREFLIGHT SCRIPT TEMPLATE
# ==========================================
# Rule: Token-Optimized CI (Silent on Success, Verbose on Failure)

PROJECT_DIR=$(dirname "$0")
TMP_TEST_LOG=$(mktemp)

echo "[$(date '+%H:%M:%S')] Starting Smart Preflight Checks..."

cd "$PROJECT_DIR" || exit 1
export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

cleanup() {
    rm -f "$TMP_TEST_LOG"
}
trap cleanup EXIT

TOTAL_PASSED=0

run_test() {
    local cmd="$1"
    local desc="$2"
    
    if ! eval "$cmd" > "$TMP_TEST_LOG" 2>&1; then
        echo "❌ PREFLIGHT FAILED: $desc"
        echo "=== ERROR DETAILS (Extracting relevant logs to save tokens) ==="
        if grep -iE -A 10 -B 2 "error:|exception|failed|unresolved|expecting|traceback|❌" "$TMP_TEST_LOG" | head -n 50; then
            :
        else
            tail -n 50 "$TMP_TEST_LOG"
        fi
        echo "==============================================================="
        exit 1
    fi
    ((TOTAL_PASSED++))
}

shopt -s nullglob

# 1. Bash Tests Discovery
# To maintain hermetic execution, we filter out heavy/flaky E2E tests and mocks.
for f in scripts/test_*.sh; do
    case "$(basename "$f")" in
        test_agent_driver_gemini.sh|test_blue_green_deploy.sh|test_cuj_*.sh|test_e2e_*.sh|test_ignition_guardrail.sh|test_kanban_runner.sh|test_secure_prompt.sh|test_state5_tier1_reset.sh|test_triad_planner.sh|test_git_boundary.sh|test_forensic_quarantine.sh|test_preflight_guardrails.sh|test_reviewer_artifact_guardrail.sh)
            continue
            ;;
    esac
    run_test "bash $f" "Bash Test: $f"
done

# 2. Python Tests Discovery
if [ -d "tests" ]; then
    test_files=(tests/test_*.py)
    if [ ${#test_files[@]} -gt 0 ]; then
        run_test "python3 -m unittest discover -s tests -p \"test_*.py\"" "Python Unittest tests/"
    fi
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

# Offline Syntax Checks
if [ -f "scripts/agent_driver.py" ]; then
    run_test "python3 -m py_compile scripts/agent_driver.py" "Syntax Check: agent_driver.py"
fi

echo "✅ $TOTAL_PASSED tests/test-suites passed."
exit 0
