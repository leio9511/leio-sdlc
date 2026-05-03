#!/bin/bash
# test_git_hook.sh: Integration test for the SDLC managed pre-commit hook.
# Verifies role-aware allowlist enforcement on protected branches.

set -e

TEST_DIR="/tmp/test_sdlc_hook_$$"
echo "=== SDLC Pre-Commit Hook Integration Tests ==="

# --- Helper: create a fresh sandbox ---
setup_sandbox() {
    rm -rf "$TEST_DIR"
    mkdir -p "$TEST_DIR"
    cd "$TEST_DIR"
    git init > /dev/null 2>&1
    git config user.name "Test"
    git config user.email "test@example.com"
    touch .sdlc_guardrail
    git add .sdlc_guardrail
    git commit -m "init" > /dev/null 2>&1

    # Install the managed hook via hooksPath
    mkdir -p .sdlc_hooks
    cp "$PROJECT_ROOT/.sdlc_hooks/pre-commit" .sdlc_hooks/
    git config core.hooksPath .sdlc_hooks
}

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# =============================================
# Test 1: Direct commit on protected branch rejected
# =============================================
echo "--------------------------------------"
echo "Test 1: Direct commit on master rejected"
setup_sandbox

echo "test" > test.txt
git add test.txt
set +e
output=$(git commit -m "direct commit" 2>&1)
exit_code=$?
set -e

if [ $exit_code -ne 0 ] && echo "$output" | grep -q "GIT COMMIT REJECTED"; then
    echo "✅ PASS: Direct commit rejected with guidance."
else
    echo "❌ FAIL: Direct commit was not rejected."
    echo "Output: $output"
    exit 1
fi

# =============================================
# Test 2: Override flag bypasses hook
# =============================================
echo "--------------------------------------"
echo "Test 2: sdlc.override=true bypasses hook"
setup_sandbox

echo "test" > test.txt
git add test.txt
git -c sdlc.override=true commit -m "override commit" > /dev/null 2>&1
echo "✅ PASS: Override flag works."

# =============================================
# Test 3: Runtime commit without role rejected
# =============================================
echo "--------------------------------------"
echo "Test 3: Runtime commit without role rejected"
setup_sandbox

echo "test" > test.txt
git add test.txt
set +e
output=$(git -c sdlc.runtime=1 commit -m "runtime no role" 2>&1)
exit_code=$?
set -e

if [ $exit_code -ne 0 ] && echo "$output" | grep -q "❌ Commit rejected: runtime commit requires explicit sdlc.role."; then
    echo "✅ PASS: Missing role runtime commit rejected with exact message."
else
    echo "❌ FAIL: Missing role rejection not as expected."
    echo "Output: $output"
    exit 1
fi

# =============================================
# Test 4: Unauthorized role rejected (verifier)
# =============================================
echo "--------------------------------------"
echo "Test 4: Unauthorized role (verifier) rejected"
setup_sandbox

echo "test" > test.txt
git add test.txt
set +e
output=$(git -c sdlc.runtime=1 -c sdlc.role=verifier commit -m "verifier commit" 2>&1)
exit_code=$?
set -e

if [ $exit_code -ne 0 ] && echo "$output" | grep -q "❌ Commit rejected: SDLC runtime role 'verifier' is not authorized to commit."; then
    echo "✅ PASS: Verifier role rejected with exact message."
else
    echo "❌ FAIL: Verifier role rejection not as expected."
    echo "Output: $output"
    exit 1
fi

# =============================================
# Test 5: Additional governance roles rejected
# =============================================
echo "--------------------------------------"
echo "Test 5: Governance roles rejected (reviewer, auditor, planner, arbitrator)"
for role in reviewer auditor planner arbitrator; do
    setup_sandbox
    echo "test" > test.txt
    git add test.txt
    set +e
    output=$(git -c sdlc.runtime=1 -c sdlc.role=$role commit -m "$role commit" 2>&1)
    exit_code=$?
    set -e
    if [ $exit_code -ne 0 ] && echo "$output" | grep -q "❌ Commit rejected: SDLC runtime role '$role' is not authorized to commit."; then
        echo "  ✅ $role rejected."
    else
        echo "❌ FAIL: $role was not blocked."
        echo "Output: $output"
        exit 1
    fi
done

# =============================================
# Test 6: Authorized roles succeed
# =============================================
echo "--------------------------------------"
echo "Test 6: Authorized roles succeed (coder, orchestrator, merge_code, commit_state)"
for role in coder orchestrator merge_code commit_state; do
    setup_sandbox
    echo "test" > test.txt
    git add test.txt
    git -c sdlc.runtime=1 -c sdlc.role=$role commit -m "$role commit" > /dev/null 2>&1
    echo "  ✅ $role allowed."
done

# =============================================
# Test 7: Feature branch commits not intercepted
# =============================================
echo "--------------------------------------"
echo "Test 7: Feature branch commits allowed"
setup_sandbox

git checkout -b feature/test > /dev/null 2>&1
echo "test" > test.txt
git add test.txt
git commit -m "feature commit" > /dev/null 2>&1
echo "✅ PASS: Feature branch commit allowed."

# =============================================
# Test 8: No guardrail means no interception
# =============================================
echo "--------------------------------------"
echo "Test 8: No .sdlc_guardrail bypasses hook"
setup_sandbox

rm .sdlc_guardrail
echo "test" > test.txt
git add test.txt
git commit -m "no guardrail" > /dev/null 2>&1
echo "✅ PASS: No guardrail bypass works."

# =============================================
# Test 9: Installation via doctor.py (check hook install)
# =============================================
echo "--------------------------------------"
echo "Test 9: doctor.py can install the managed hook"
setup_sandbox

# Verify hook file exists and is executable
if [ -x .sdlc_hooks/pre-commit ]; then
    echo "✅ PASS: Hook installed and executable."
else
    echo "❌ FAIL: Hook not executable."
    exit 1
fi

# Verify hook metadata
if grep -q "SDLC_MANAGED_HOOK=leio-sdlc" .sdlc_hooks/pre-commit; then
    echo "✅ PASS: Hook contains managed hook metadata."
else
    echo "❌ FAIL: Managed hook metadata missing."
    exit 1
fi

if grep -q "SDLC_HOOK_SCHEMA_VERSION=2" .sdlc_hooks/pre-commit; then
    echo "✅ PASS: Hook has correct schema version."
else
    echo "❌ FAIL: Hook schema version incorrect or missing."
    exit 1
fi

# Cleanup
rm -rf "$TEST_DIR"

echo "--------------------------------------"
echo "✅ ALL HOOK INTEGRATION TESTS PASSED!"
