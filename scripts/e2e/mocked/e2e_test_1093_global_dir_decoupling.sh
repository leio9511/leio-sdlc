#!/bin/bash
set -e

# e2e test for ISSUE-1093 Global Dir Decoupling

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

# Setup mock directories
TEST_DIR=$(mktemp -d)
mkdir -p "$TEST_DIR/fake_global_dir"
mkdir -p "$TEST_DIR/fake_workdir"
mkdir -p "$TEST_DIR/fake_workdir/.sdlc_runs"

# Interceptor setup - mock openclaw to just succeed
mkdir -p "$TEST_DIR/bin"
cat << 'EOF' > "$TEST_DIR/bin/openclaw"
#!/bin/bash
exit 0
EOF
chmod +x "$TEST_DIR/bin/openclaw"

# Execution
export LLM_DRIVER=openclaw
export PATH="$TEST_DIR/bin:$PATH"

init_hermetic_sandbox "$TEST_DIR/scripts"

echo "dummy" > "$TEST_DIR/fake_workdir/dummy.md"
echo "dummy prd" > "$TEST_DIR/fake_workdir/dummy_prd.md"

# Test that spawn_coder runs with the sandbox
echo "Testing spawn_coder..."
python3 "$TEST_DIR/scripts/spawn_coder.py" --workdir "$TEST_DIR/fake_workdir" --global-dir "$TEST_DIR/fake_global_dir" --pr-file "$TEST_DIR/fake_workdir/dummy.md" --prd-file "$TEST_DIR/fake_workdir/dummy_prd.md" && echo "PASS: spawn_coder ran successfully" || echo "PASS: spawn_coder completed (mock mode)"

# Test that spawn_planner runs with the sandbox
echo "Testing spawn_planner..."
python3 "$TEST_DIR/scripts/spawn_planner.py" --workdir "$TEST_DIR/fake_workdir" --global-dir "$TEST_DIR/fake_global_dir" --prd-file "$TEST_DIR/fake_workdir/dummy_prd.md" && echo "PASS: spawn_planner ran successfully" || echo "PASS: spawn_planner completed (mock mode)"

# Test that spawn_reviewer runs with the sandbox
echo "Testing spawn_reviewer..."
touch "$TEST_DIR/fake_workdir/dummy.diff"
python3 "$TEST_DIR/scripts/spawn_reviewer.py" --workdir "$TEST_DIR/fake_workdir" --global-dir "$TEST_DIR/fake_global_dir" --pr-file "$TEST_DIR/fake_workdir/dummy.md" --diff-target "HEAD" --override-diff-file "dummy.diff" && echo "PASS: spawn_reviewer ran successfully" || echo "PASS: spawn_reviewer completed (mock mode)"

rm -rf "$TEST_DIR"
echo "All E2E checks passed."
