#!/bin/bash
export SDLC_TEST_MODE=true
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR=$(mktemp -d)
mkdir -p "$SANDBOX_DIR/bin"
cat << 'INNER_EOF' > "$SANDBOX_DIR/bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
chmod +x "$SANDBOX_DIR/bin/openclaw"
export PATH="$SANDBOX_DIR/bin:$PATH"
echo "Sandbox: $SANDBOX_DIR"

init_hermetic_sandbox "$SANDBOX_DIR/scripts"

cd "$SANDBOX_DIR"
# No git init here
touch prd.md

if python3 "$SANDBOX_DIR/scripts/orchestrator.py" --force-replan false --enable-exec-from-workspace --workdir "$(pwd)" --prd-file prd.md --channel "valid:id" --global-dir "$(pwd)" 2>&1 | grep -i "git boundary violation"; then
    echo "✅ test_git_boundary.sh PASSED"
else
    echo "❌ test_git_boundary.sh FAILED: Did not enforce git boundary."
    python3 "$SANDBOX_DIR/scripts/orchestrator.py" --force-replan false --enable-exec-from-workspace --workdir "$(pwd)" --prd-file prd.md --channel "valid:id" --global-dir "$(pwd)" 2>&1
    exit 1
fi
rm -rf "$SANDBOX_DIR"
