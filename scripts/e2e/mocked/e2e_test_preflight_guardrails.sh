#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

echo "Starting Pre-flight Guardrails Test..."

# 1. Initialize Sandbox
TEST_DIR=$(mktemp -d -t sdlc_guardrails_test_XXXXXX)
echo "Sandbox created at $TEST_DIR"

init_hermetic_sandbox "$TEST_DIR/scripts"

cd "$TEST_DIR"
git init >/dev/null 2>&1
git config user.email "test@example.com"
git config user.name "Test User"
git commit --allow-empty -m "init" >/dev/null 2>&1

export SDLC_TEST_MODE=true

create_preflight_fixture() {
    local sandbox_dir="$1"
    mkdir -p "$sandbox_dir/scripts" "$sandbox_dir/tests"
    cp "$PROJECT_ROOT/preflight.sh" "$sandbox_dir/preflight.sh"
    chmod +x "$sandbox_dir/preflight.sh"
    cat > "$sandbox_dir/tests/test_template_compliance.py" <<'PY'
def test_template_compliance_placeholder():
    assert True
PY
}

run_sandbox_preflight() {
    local sandbox_dir="$1"
    set +e
    PREFLIGHT_OUTPUT=$(cd "$sandbox_dir" && bash ./preflight.sh 2>&1)
    PREFLIGHT_EXIT=$?
    set -e
}

# 2. Test Planner Pre-flight
echo "Testing Planner Pre-flight..."
set +e
output=$(python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file missing.md --workdir . --global-dir . 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Planner exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Planner did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# 3. Test Coder Pre-flight
echo "Testing Coder Pre-flight..."
git checkout -b feature/dummy-guardrails >/dev/null 2>&1
set +e
output=$(python3 scripts/spawn_coder.py --enable-exec-from-workspace --pr-file missing.md --prd-file missing.md --workdir . --global-dir . 2>&1)
exit_code=$?
set -e
git checkout master >/dev/null 2>&1
if [ $exit_code -ne 1 ]; then
    echo "Fail: Coder exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Coder did not output [Pre-flight Failed]"
    echo "Output was: $output"
    exit 1
fi

# 4. Test Reviewer Pre-flight
echo "Testing Reviewer Pre-flight..."
# Create a dummy PR file to satisfy file check, but it should still fail status check or logic
echo "---
status: open
---" > PR.md
set +e
output=$(python3 scripts/spawn_reviewer.py --enable-exec-from-workspace --pr-file PR.md --diff-target HEAD --workdir . --global-dir . 2>&1)
exit_code=$?
set -e

# 5. Test Merge Pre-flight
echo "Testing Merge Pre-flight..."
# Action 1: fake review file
set +e
output=$(python3 scripts/merge_code.py --branch fake-branch --review-file missing.md 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Merge exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Merge did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# Action 2: {"overall_assessment": "NEEDS_IMMEDIATE_REWORK"} without force
echo '{"overall_assessment": "NEEDS_IMMEDIATE_REWORK"}' > review.md
set +e
output=$(python3 scripts/merge_code.py --branch fake-branch --review-file review.md 2>&1)
exit_code=$?
set -e
if [ $exit_code -ne 1 ]; then
    echo "Fail: Merge exit code is not 1 (got $exit_code)"
    exit 1
fi
if ! echo "$output" | grep -q "\[Pre-flight Failed\]"; then
    echo "Fail: Merge did not output [Pre-flight Failed]"
    echo "Output: $output"
    exit 1
fi

# Action 3: {"overall_assessment": "NEEDS_IMMEDIATE_REWORK"} with force
echo "Testing Merge with force-approved..."
set +e
python3 scripts/merge_code.py --branch fake-branch --review-file review.md --force-approved >/dev/null 2>&1
exit_code=$?
set -e
if [ $exit_code -ne 0 ]; then
    echo "Fail: Merge should have succeeded with force-approved"
    exit 1
fi

# Action 4: {"overall_assessment": "EXCELLENT"}
echo "Testing Merge with APPROVED..."
echo '{"overall_assessment": "EXCELLENT"}' > review2.md
set +e
python3 scripts/merge_code.py --branch fake-branch --review-file review2.md >/dev/null 2>&1
exit_code=$?
set -e
if [ $exit_code -ne 0 ]; then
    echo "Fail: Merge should have succeeded with APPROVED"
    exit 1
fi

# 6. Test config-driven preflight ignore list

echo "Testing config-driven preflight ignore list..."

# Test Case 1: test_non_empty_ignore_manifest_skips_listed_bash_and_pytest_targets_and_returns_quarantine_green
PREFLIGHT_SANDBOX=$(mktemp -d -t sdlc_preflight_ignore_non_empty_XXXXXX)
create_preflight_fixture "$PREFLIGHT_SANDBOX"
cat > "$PREFLIGHT_SANDBOX/scripts/test_ignored_bash.sh" <<'SH'
#!/bin/bash
echo "IGNORED_BASH_RAN"
exit 1
SH
chmod +x "$PREFLIGHT_SANDBOX/scripts/test_ignored_bash.sh"
cat > "$PREFLIGHT_SANDBOX/scripts/test_allowed_bash.sh" <<'SH'
#!/bin/bash
echo "ALLOWED_BASH_RAN"
exit 0
SH
chmod +x "$PREFLIGHT_SANDBOX/scripts/test_allowed_bash.sh"
cat > "$PREFLIGHT_SANDBOX/tests/test_ignored_pytest.py" <<'PY'
def test_ignored_pytest():
    print("IGNORED_PYTEST_RAN")
    assert False
PY
cat > "$PREFLIGHT_SANDBOX/tests/test_allowed_pytest.py" <<'PY'
def test_allowed_pytest():
    assert True
PY
cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{
  "bash": [
    "scripts/test_ignored_bash.sh"
  ],
  "pytest": [
    "tests/test_ignored_pytest.py"
  ]
}
JSON
run_sandbox_preflight "$PREFLIGHT_SANDBOX"
if [ $PREFLIGHT_EXIT -ne 0 ]; then
    echo "Fail: non-empty ignore manifest should produce quarantine green"
    echo "$PREFLIGHT_OUTPUT"
    exit 1
fi
if ! echo "$PREFLIGHT_OUTPUT" | grep -q "debt-quarantine green"; then
    echo "Fail: quarantine-green marker was not observable"
    echo "$PREFLIGHT_OUTPUT"
    exit 1
fi
if echo "$PREFLIGHT_OUTPUT" | grep -q "IGNORED_BASH_RAN\|IGNORED_PYTEST_RAN"; then
    echo "Fail: ignored sentinel target executed"
    echo "$PREFLIGHT_OUTPUT"
    exit 1
fi
rm -rf "$PREFLIGHT_SANDBOX"

# Test Case 2: test_empty_ignore_manifest_restores_full_preflight_surface
PREFLIGHT_SANDBOX=$(mktemp -d -t sdlc_preflight_ignore_empty_XXXXXX)
create_preflight_fixture "$PREFLIGHT_SANDBOX"
cat > "$PREFLIGHT_SANDBOX/scripts/test_unignored_bash.sh" <<'SH'
#!/bin/bash
echo "UNIGNORED_BASH_RAN"
exit 1
SH
chmod +x "$PREFLIGHT_SANDBOX/scripts/test_unignored_bash.sh"
cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{
  "bash": [],
  "pytest": []
}
JSON
run_sandbox_preflight "$PREFLIGHT_SANDBOX"
if [ $PREFLIGHT_EXIT -eq 0 ]; then
    echo "Fail: empty ignore manifest should restore full discovery and fail on failing bash sentinel"
    echo "$PREFLIGHT_OUTPUT"
    exit 1
fi
if ! echo "$PREFLIGHT_OUTPUT" | grep -q "Bash Test: scripts/test_unignored_bash.sh"; then
    echo "Fail: empty manifest did not expose full bash discovery surface"
    echo "$PREFLIGHT_OUTPUT"
    exit 1
fi
rm -rf "$PREFLIGHT_SANDBOX"

# Test Case 3: test_missing_or_malformed_ignore_manifest_fails_closed
for manifest_case in missing invalid_json unknown_key wrong_type wrong_item_type; do
    PREFLIGHT_SANDBOX=$(mktemp -d -t "sdlc_preflight_ignore_${manifest_case}_XXXXXX")
    create_preflight_fixture "$PREFLIGHT_SANDBOX"
    case "$manifest_case" in
        missing)
            ;;
        invalid_json)
            cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{ invalid json
JSON
            ;;
        unknown_key)
            cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{
  "bash": [],
  "pytest": [],
  "node": []
}
JSON
            ;;
        wrong_type)
            cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{
  "bash": "scripts/test_example.sh",
  "pytest": []
}
JSON
            ;;
        wrong_item_type)
            cat > "$PREFLIGHT_SANDBOX/ignore_tests.json" <<'JSON'
{
  "bash": [],
  "pytest": [123]
}
JSON
            ;;
    esac
    run_sandbox_preflight "$PREFLIGHT_SANDBOX"
    if [ $PREFLIGHT_EXIT -eq 0 ]; then
        echo "Fail: malformed ignore manifest case '$manifest_case' should fail closed"
        echo "$PREFLIGHT_OUTPUT"
        exit 1
    fi
    if ! echo "$PREFLIGHT_OUTPUT" | grep -q "If ignore_tests.json is missing or malformed, preflight must fail closed."; then
        echo "Fail: fail-closed statement missing for case '$manifest_case'"
        echo "$PREFLIGHT_OUTPUT"
        exit 1
    fi
    rm -rf "$PREFLIGHT_SANDBOX"
done

# Test Case 4: test_seed_manifest_matches_prd_quarantine_list_exactly
python3 - "$PROJECT_ROOT/ignore_tests.json" <<'PY'
import json
import sys

expected = {
    "bash": [
        "scripts/test_planner_slice_failed_pr.sh"
    ],
    "pytest": [
        "tests/test_orchestrator_session_strategy.py",
        "tests/test_079_agent_driver_openclaw_lazy_create.py",
        "tests/test_083_openclaw_model_aware_routing.py",
        "tests/test_handoff_integration.py",
        "tests/test_orchestrator_handoff.py",
        "tests/test_planner_envelope_forward_compatibility.py",
        "tests/test_spawn_auditor.py",
    ],
}
with open(sys.argv[1], "r", encoding="utf-8") as f:
    actual = json.load(f)
assert actual == expected, actual
PY

# 7. Cleanup Sandbox
echo "[GUARDRAILS_TEST_SUCCESS]"
rm -rf "$TEST_DIR"
