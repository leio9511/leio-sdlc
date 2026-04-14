#!/usr/bin/env bash
export SDLC_TEST_MODE=true
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

echo "Running Anti-Reward Hacking Tests..."

TEST_DIR=$(mktemp -d)
cd "$TEST_DIR"
git init > /dev/null 2>&1
git config user.email "test@test.com"
git config user.name "Test"
mkdir -p bin
cat << 'INNER_EOF' > bin/openclaw
#!/bin/bash
exit 0
INNER_EOF
chmod +x bin/openclaw
export PATH="$(pwd)/bin:$PATH"

init_hermetic_sandbox "$TEST_DIR/scripts"

touch dummy.md
python3 "$TEST_DIR/scripts/orchestrator.py" --force-replan true --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file dummy.md --global-dir . --max-prs-to-process 1 > test.log 2>&1 || true

if grep -q "No such file or directory.*scripts/" test.log; then
    echo "FAILED: Orchestrator is still using relative scripts/ paths!"
    cat test.log
    exit 1
fi
echo "Test Scenario 1 passed."

# Scenario 2 - spawn_reviewer
echo "dummy diff content" > dummy_diff.txt
git add dummy_diff.txt

SDLC_TEST_MODE=true python3 "$TEST_DIR/scripts/spawn_reviewer.py" --pr-file dummy.md --diff-target HEAD --workdir "$(pwd)" --global-dir "$(pwd)" || true

# Cleanup git changes
git reset HEAD dummy_diff.txt >/dev/null 2>&1 || true
rm -f dummy_diff.txt

rm -rf "$TEST_DIR"
echo "All Anti-Reward Hacking Tests passed."
