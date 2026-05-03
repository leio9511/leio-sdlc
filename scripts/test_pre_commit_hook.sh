#!/bin/bash
set -e

echo "=== Testing Pre-Commit Hook Integration ==="

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Setup Sandbox
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"
git init > /dev/null
git config user.name "Test"
git config user.email "test@example.com"
touch .sdlc_guardrail
git add .sdlc_guardrail
git commit -m "init" > /dev/null
cp -r "$WORKSPACE_ROOT/.sdlc_hooks" .

# 2. Configure hooksPath
git config core.hooksPath .sdlc_hooks

# 3. Test: Raw commit on master should fail
echo "Test 1: Expecting rejection for raw commit on master..."
set +e
git commit --allow-empty -m "direct commit" > commit.log 2>&1
EXIT_CODE=$?
set -e
if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ FAILED: Direct commit on master was not blocked."
    exit 1
fi
if ! grep -q "GIT COMMIT REJECTED" commit.log; then
    echo "❌ FAILED: Rejection message not found."
    exit 1
fi
if ! grep -q "python3 ~/.openclaw/skills/leio-sdlc/scripts/commit_state.py" commit.log; then
    echo "❌ FAILED: Missing commit_state.py instruction in pre-commit hook output."
    exit 1
fi
echo "✅ PASSED: Raw commit rejected as expected."

# 4. Test: Override flag should succeed
echo "Test 2: Expecting success with override flag..."
git -c sdlc.override=true commit --allow-empty -m "override commit"
echo "✅ PASSED: Override flag works as expected."

# 5. Test: Runtime flag without role should fail
echo "Test 3: Expecting rejection for runtime flag without role..."
set +e
git -c sdlc.runtime=1 commit --allow-empty -m "runtime commit missing role" > runtime-missing-role.log 2>&1
EXIT_CODE=$?
set -e
if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ FAILED: Runtime commit without role was not blocked."
    exit 1
fi
if ! grep -q "❌ Commit rejected: runtime commit requires explicit sdlc.role." runtime-missing-role.log; then
    echo "❌ FAILED: Missing explicit-role rejection message."
    exit 1
fi
echo "✅ PASSED: Runtime commit without role rejected."

# 6. Test: Unauthorized runtime role should fail
echo "Test 4: Expecting rejection for unauthorized runtime role..."
set +e
git -c sdlc.runtime=1 -c sdlc.role=verifier commit --allow-empty -m "runtime commit verifier" > runtime-unauthorized-role.log 2>&1
EXIT_CODE=$?
set -e
if [ $EXIT_CODE -eq 0 ]; then
    echo "❌ FAILED: Unauthorized runtime role was not blocked."
    exit 1
fi
if ! grep -q "❌ Commit rejected: SDLC runtime role 'verifier' is not authorized to commit." runtime-unauthorized-role.log; then
    echo "❌ FAILED: Missing unauthorized-role rejection message."
    exit 1
fi
echo "✅ PASSED: Unauthorized runtime role rejected."

# 7. Test: Authorized runtime role should succeed
echo "Test 5: Expecting success with authorized runtime role..."
git -c sdlc.runtime=1 -c sdlc.role=coder commit --allow-empty -m "runtime commit coder"
echo "✅ PASSED: Authorized runtime role works as expected."

# 8. Test: Commit on feature branch should succeed
echo "Test 6: Expecting success on feature branch..."
git checkout -b feature/test > /dev/null
git commit --allow-empty -m "feature commit"
echo "✅ PASSED: Commit on feature branch allowed."

# 9. Test: No guardrail file should succeed
echo "Test 7: Expecting success without .sdlc_guardrail..."
git checkout master > /dev/null
rm .sdlc_guardrail
git commit --allow-empty -m "no guardrail commit"
echo "✅ PASSED: Commit without guardrail allowed."


rm -rf "$SANDBOX_DIR"
echo "✅ All pre-commit hook tests passed."
