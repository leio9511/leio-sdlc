#!/bin/bash
set -e

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Sandbox created at $TEMP_DIR"

# Paths to scripts being tested
CREATE_PR="$(pwd)/scripts/create_pr_contract.py"
GET_NEXT_PR="$(pwd)/scripts/get_next_pr.py"
SPAWN_PLANNER="$(pwd)/scripts/spawn_planner.py"
SPAWN_CODER="$(pwd)/scripts/spawn_coder.py"

echo "=== T1: Fail-Fast Missing Arg ==="
if python3 "$CREATE_PR" --job-dir "docs/PRs" --title "Test" --content-file "test.md" 2>/dev/null; then
    echo "❌ T1 Failed: create_pr_contract.py should require --workdir"
    exit 1
fi

if python3 "$GET_NEXT_PR" --job-dir "docs/PRs" 2>/dev/null; then
    echo "❌ T1 Failed: get_next_pr.py should require --workdir"
    exit 1
fi
echo "✅ T1 Passed"

echo "=== T2: Relative Path Normalization ==="
# Test with a relative path for workdir
mkdir -p "$TEMP_DIR/tmp_test" && git -C "$TEMP_DIR/tmp_test" init > /dev/null
echo "Dummy content" > "$TEMP_DIR/tmp_test/dummy.md"

cd "$TEMP_DIR" # Move out of project root to test relative resolution correctly
if ! python3 "$CREATE_PR" --workdir "./tmp_test" --job-dir "./tmp_test/docs/PRs" --title "Test Rel" --content-file "./tmp_test/dummy.md"; then
    echo "❌ T2 Failed: create_pr_contract.py did not handle relative workdir properly"
    exit 1
fi
echo "✅ T2 Passed"

echo "=== T3: Strict Sandbox Isolation (Coder/Planner) ==="
export SDLC_TEST_MODE="true"
mkdir -p "$TEMP_DIR/t3_sandbox"
echo "PRD CONTENT" > "$TEMP_DIR/t3_sandbox/prd.md"
echo "PR CONTENT" > "$TEMP_DIR/t3_sandbox/pr.md"

cd "$TEMP_DIR/t3_sandbox"
python3 "$SPAWN_CODER" --pr-file "pr.md" --prd-file "prd.md" --workdir . --global-dir /root/.openclaw/workspace/projects/leio-sdlc > /dev/null

if [ ! -d "$TEMP_DIR/t3_sandbox/tests" ]; then
    echo "❌ T3 Failed: Coder did not generate mock output inside the ephemeral sandbox."
    exit 1
fi

if [ -d "/root/.openclaw/workspace/projects/leio-sdlc/tests" ]; then
    grep -q "spawn_coder" "$TEMP_DIR/t3_sandbox/tests/tool_calls.log" || { echo "❌ T3 Failed: Log not found"; exit 1; }
fi
echo "✅ T3 Passed"

echo "=== T4: Toolchain Dynamic Path Resolution ==="
cd "$TEMP_DIR/t3_sandbox"
python3 "$SPAWN_PLANNER" --prd-file "prd.md" --out-dir "docs/PRs" --workdir . --global-dir /root/.openclaw/workspace/projects/leio-sdlc > /dev/null

if ! grep -q "create_pr_contract.py" "$TEMP_DIR/t3_sandbox/tests/tool_calls.log"; then
    echo "❌ T4 Failed: Planner mock did not capture create_pr_contract.py dynamic path."
    exit 1
fi
# check absolute path for create_pr_contract.py
if grep -q "'contract_script': '/root/.openclaw/workspace/projects/leio-sdlc/scripts/create_pr_contract.py'" "$TEMP_DIR/t3_sandbox/tests/tool_calls.log"; then
    echo "✅ T4 Passed"
else
    echo "❌ T4 Failed: Planner did not use absolute path for create_pr_contract.py"
    cat "$TEMP_DIR/t3_sandbox/tests/tool_calls.log"
    exit 1
fi

unset SDLC_TEST_MODE

echo "=== T5: Path Traversal Rejection ==="
cd "$TEMP_DIR"
# Try to write outside the workdir
if python3 "$CREATE_PR" --workdir "$TEMP_DIR/tmp_test" --job-dir "../../../../../tmp" --title "Malicious" --content-file "$TEMP_DIR/tmp_test/dummy.md" 2>&1 | grep -q "SecurityError"; then
    echo "✅ T5 Passed (Blocked job-dir traversal)"
else
    echo "❌ T5 Failed: create_pr_contract.py allowed path traversal for job-dir"
    exit 1
fi

if python3 "$CREATE_PR" --workdir "$TEMP_DIR/tmp_test" --job-dir "$TEMP_DIR/tmp_test/docs/PRs" --title "Malicious2" --content-file "../../../../../etc/passwd" 2>&1 | grep -q "SecurityError"; then
    echo "✅ T5 Passed (Blocked content-file traversal)"
else
    echo "❌ T5 Failed: create_pr_contract.py allowed path traversal for content-file"
    exit 1
fi

echo "✅ All guardrail tests passed."
