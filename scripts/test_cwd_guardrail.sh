#!/bin/bash
export SDLC_TEST_MODE=true
set -euo pipefail

# test_cwd_guardrail.sh
# Ensures that SDLC scripts correctly enforce working directory boundaries.

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEMP_DIR="$(mktemp -d)"
HOME_DIR="$(mktemp -d)"
mkdir -p "$TEMP_DIR/bin"
cat << 'INNER_EOF' > "$TEMP_DIR/bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
chmod +x "$TEMP_DIR/bin/openclaw"
export PATH="$TEMP_DIR/bin:$PATH"
export HOME="$HOME_DIR"
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

trap 'rm -rf "$TEMP_DIR" "$HOME_DIR"' EXIT

echo "Sandbox: $TEMP_DIR"

# 1. Test Boundary Violation (No .git in workdir but .git in parent)
OUTER_REPO="$TEMP_DIR/outer_repo"
mkdir -p "$OUTER_REPO"
init_git_test_sandbox "$OUTER_REPO"

INNER_DIR="$OUTER_REPO/inner_dir"
mkdir -p "$INNER_DIR"

echo "--- Testing Boundary Violation Detection ---"
cd "$PROJECT_ROOT"
BOUNDARY_OUTPUT="$("$DEV_PYTHON" scripts/orchestrator.py --enable-exec-from-workspace --force-replan true --enable-exec-from-workspace --enable-exec-from-workspace --workdir "$INNER_DIR" --prd-file "prd.md" --channel "valid:id" --global-dir "$PROJECT_ROOT" 2>&1 || true)"
if echo "$BOUNDARY_OUTPUT" | grep -qi "git boundary violation"; then
    echo "✅ Success: Boundary violation detected."
else
    echo "❌ FAILED: Boundary violation NOT detected."
    echo "$BOUNDARY_OUTPUT"
    exit 1
fi

# 2. Test Correct Operation (With .git in workdir)
echo "--- Testing Correct Operation with CWD ---"
init_git_test_sandbox "$INNER_DIR"
cd "$INNER_DIR"
touch prd.md
git add prd.md
git commit -m "init" > /dev/null

cd "$PROJECT_ROOT"
VALID_REPO_OUTPUT="$("$DEV_PYTHON" scripts/orchestrator.py --enable-exec-from-workspace --force-replan true --enable-exec-from-workspace --enable-exec-from-workspace --workdir "$INNER_DIR" --prd-file "prd.md" --channel "valid:id" --global-dir "$PROJECT_ROOT" 2>&1 || true)"
if echo "$VALID_REPO_OUTPUT" | grep -qi "git boundary violation"; then
    echo "❌ FAILED: Boundary violation detected on a valid git repo."
    echo "$VALID_REPO_OUTPUT"
    exit 1
else
    echo "✅ Success: Passed boundary check."
fi

echo "✅ All CWD Guardrail tests passed."
