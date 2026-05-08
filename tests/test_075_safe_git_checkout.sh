#!/usr/bin/env bash
export SDLC_TEST_MODE=true
set -e

# Setup test environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_DIR=$(mktemp -d)

source "$SCRIPT_DIR/../scripts/e2e/setup_sandbox.sh"

cd "$TEST_DIR"
init_git_test_sandbox "$TEST_DIR"

# Copy root .gitignore to ignore orchestrator runtime files
cp "$SCRIPT_DIR/../.gitignore" "$TEST_DIR/.gitignore"

echo "dummy content" > README.md
git add README.md .gitignore
git commit -m "initial commit" > /dev/null

# Make repo SDLC compliant so orchestrator doesn't fail early
python3 "$SCRIPT_DIR/../scripts/doctor.py" "$TEST_DIR" --fix > /dev/null 2>&1

# Create a fake PRD and PR
mkdir -p docs/PRDs docs/PRs/dummy_prd
echo "# Dummy PRD" > docs/PRDs/dummy_prd.md
cat << 'PR_EOF' > docs/PRs/dummy_prd/PR_001_dummy.md
status: in_progress
slice_depth: 0

# Dummy PR
PR-001
PR_EOF

git add .
git commit -m "add prd and sdlc infra" > /dev/null

# Simulate a failure by breaking git checkout specifically
# We'll put a broken git script in front of the PATH
FAKE_BIN_DIR=$(mktemp -d)
cat << 'GIT_EOF' > "$FAKE_BIN_DIR/git"
#!/bin/bash
if [[ "$1" == "checkout" ]]; then
    echo "Simulated git checkout failure!" >&2
    exit 1
fi
exec /usr/bin/git "$@"
GIT_EOF
chmod +x "$FAKE_BIN_DIR/git"

# Run orchestrator
export PATH="$FAKE_BIN_DIR:$PATH"

echo "Running orchestrator..."
set +e
/usr/bin/python3 "$SCRIPT_DIR/../scripts/orchestrator.py" --enable-exec-from-workspace --force-replan true --channel "valid:id" \
    --prd-file docs/PRDs/dummy_prd.md \
    --workdir "$TEST_DIR" \
    --max-prs-to-process 1 > orchestrator.log 2>&1
EXIT_CODE=$?
set -e

cat orchestrator.log

# Assertions
if ! grep -q "Workspace preserved." orchestrator.log; then
    echo "ERROR: Orchestrator did not catch git checkout failure gracefully."
    exit 1
fi

if ! grep -q "Simulated git checkout failure!" orchestrator.log; then
    echo "ERROR: Did not see the simulated failure in logs."
    exit 1
fi

# Ensure files were not deleted
if [ ! -f "docs/PRDs/dummy_prd.md" ]; then
    echo "ERROR: Orchestrator destructively deleted files."
    exit 1
fi

echo "Test 075 Passed"
rm -rf "$TEST_DIR"
exit 0
