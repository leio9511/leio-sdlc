#!/bin/bash
set -e

echo "================================================="
echo "Testing: Role Continuity Contracts"
echo "================================================="

WORK_DIR=$(mktemp -d)

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

cp -r "$(cd "$(dirname "$0")/.." && pwd)"/* "$WORK_DIR/"
cd "$WORK_DIR"

export SDLC_MOCK_LLM_RESPONSE="OK"
export SDLC_TEST_MODE="false"  # Ensure we hit invoke_agent

mkdir -p "$WORK_DIR/docs/PRDs"
echo "Test PR" > "$WORK_DIR/docs/PRDs/dummy.md"
echo "Test PR" > "$WORK_DIR/dummy_pr.md"

# 1. Coder (Persists)
python3 scripts/spawn_coder.py --enable-exec-from-workspace --pr-file dummy_pr.md --prd-file docs/PRDs/dummy.md --workdir . --run-dir . > /dev/null 2>&1 || true
if [ ! -f ".coder_session" ]; then
    echo "❌ Coder did not persist .coder_session"
    exit 1
fi
echo "✅ Coder session persisted via .coder_session"

# 2. Reviewer (Persists)
python3 scripts/spawn_reviewer.py --enable-exec-from-workspace --pr-file dummy_pr.md --prd-file docs/PRDs/dummy.md --diff-target HEAD --workdir . --run-dir . > /dev/null 2>&1 || true
if [ ! -f ".reviewer_session" ]; then
    echo "❌ Reviewer did not persist .reviewer_session"
    exit 1
fi
echo "✅ Reviewer session persisted via .reviewer_session"

# 3. Planner (No Persist)
python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file docs/PRDs/dummy.md --workdir . --run-dir . > /dev/null 2>&1 || true
if [ -f ".planner_session" ]; then
    echo "❌ Planner persisted .planner_session"
    exit 1
fi
echo "✅ Planner session not persisted"

# 4. Verifier (No Persist)
python3 scripts/spawn_verifier.py --enable-exec-from-workspace --prd-files docs/PRDs/dummy.md --workdir . > /dev/null 2>&1 || true
if [ -f ".verifier_session" ]; then
    echo "❌ Verifier persisted .verifier_session"
    exit 1
fi
echo "✅ Verifier session not persisted"

echo "✅ test_082_role_continuity_contracts.sh passed."
exit 0
