#!/bin/bash
export SDLC_TEST_MODE=true
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR="$(mktemp -d)"
HOME_DIR="$(mktemp -d)"
trap 'rm -rf "$SANDBOX_DIR" "$HOME_DIR"' EXIT

mkdir -p "$SANDBOX_DIR/bin"
cat << 'INNER_EOF' > "$SANDBOX_DIR/bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
chmod +x "$SANDBOX_DIR/bin/openclaw"
export PATH="$SANDBOX_DIR/bin:$PATH"
export HOME="$HOME_DIR"
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

echo "Sandbox: $SANDBOX_DIR"

cd "$SANDBOX_DIR"
init_git_test_sandbox "$(pwd)"
"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1
git add .
git commit -m "init" > /dev/null

# Run orchestrator in a sub-process so we can kill it after checking the lock
# We use --test-sleep to make it wait
"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --enable-exec-from-workspace --workdir "$(pwd)" --prd-file prd.md --test-sleep --channel "valid:id" --global-dir "$(pwd)" &
PID=$!
for _ in {1..20}; do
    if [ -f .sdlc_repo.lock ]; then
        break
    fi
    sleep 0.25
done

if [ ! -f .sdlc_repo.lock ]; then
    echo "❌ test_polyrepo_context.sh FAILED: .sdlc_repo.lock not found in workdir."
    kill $PID || true
    exit 1
fi

kill $PID || true
echo "✅ test_polyrepo_context.sh PASSED"
