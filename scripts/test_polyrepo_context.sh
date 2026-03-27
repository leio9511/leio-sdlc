#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
echo "Sandbox: $SANDBOX_DIR"

cd "$SANDBOX_DIR"
git init > /dev/null
git config user.name "Test"
git config user.email "test@example.com"
git commit --allow-empty -m "init"

# Run orchestrator in a sub-process so we can kill it after checking the lock
# We use --test-sleep to make it wait
python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --workdir "$(pwd)" --prd-file prd.md --test-sleep --channel "#test" --global-dir "$(pwd)" &
PID=$!
sleep 1

if [ ! -f .sdlc_repo.lock ]; then
    echo "❌ test_polyrepo_context.sh FAILED: .sdlc_repo.lock not found in workdir."
    kill $PID || true
    exit 1
fi

kill $PID || true
echo "✅ test_polyrepo_context.sh PASSED"
rm -rf "$SANDBOX_DIR"
