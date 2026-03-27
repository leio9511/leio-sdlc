#!/bin/bash
export SDLC_TEST_MODE=true
set -e

# test_escalation_clean.sh - Verify workspace cleanup logic in State 5 Escalation

# State flag must be outside the sandbox, as the sandbox is deleted.
FLAG_FILE="/tmp/coder_failed_once.flag"
rm -f "$FLAG_FILE"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"

git init > /dev/null 2>&1
git config user.name "E2E Test"
git config user.email "e2e@example.com"

echo "initial" > init.txt
git add init.txt
git commit -m "init" > /dev/null 2>&1

mkdir -p docs/PRs/dummy_prd scripts
cp "${PROJECT_ROOT}/scripts/orchestrator.py" scripts/
cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/

echo ".sdlc_run.lock" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.log" >> .gitignore
git add .gitignore scripts docs
git commit -m "setup" > /dev/null 2>&1

cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
INNER_EOF

# Mock Coder: make dirty workspace and fail ONCE
cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
flag_file = "/tmp/coder_failed_once.flag"
if not os.path.exists(flag_file):
    with open(flag_file, "w") as f:
        f.write("yes")
    # Make workspace dirty and fail
    with open("dirty_untracked.txt", "w") as f: f.write("dirty")
    with open("init.txt", "w") as f: f.write("modified")
    sys.exit(1) # Fail the first time
else:
    # On the second run, succeed. The orchestrator will clean up the flag.
    sys.exit(0)
INNER_EOF

cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF

cat << 'INNER_EOF' > scripts/spawn_arbitrator.py
import sys
sys.exit(1)
INNER_EOF

chmod +x scripts/*.py
git add .
git add -A && git commit -m "pre-run clean state" > /dev/null 2>&1

echo "DEBUG: git status before orchestrator"
git status
# Run Orchestrator
export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
SDLC_BYPASS_BRANCH_CHECK=1 python3 scripts/orchestrator.py --enable-exec-from-workspace --channel "valid:id" --channel "valid:id" --workdir "$(pwd)" --global-dir "$PROJECT_ROOT" --prd-file dummy_prd.md --max-prs-to-process 2 --coder-session-strategy always > orchestrator.log 2>&1 || true

# Assertions
echo "--- Orchestrator Log ---"
cat orchestrator.log
echo "-----------------------"

if [ -f "dirty_untracked.txt" ]; then
    echo "❌ test_escalation_clean.sh FAILED: dirty_untracked.txt still exists."
    exit 1
fi

MODIFIED_CONTENT=$(cat init.txt)
if [ "$MODIFIED_CONTENT" != "initial" ]; then
    echo "❌ test_escalation_clean.sh FAILED: init.txt was not reset to its original state."
    exit 1
fi

if ! grep -q "Tier 1 (Reset): Deleting branch and retrying." orchestrator.log; then
    echo "❌ test_escalation_clean.sh FAILED: Escalation Tier 1 was not logged."
    exit 1
fi

if ! grep -q "No open PRs found. Exiting." orchestrator.log; then
    echo "❌ test_escalation_clean.sh FAILED: Orchestrator did not successfully close the PR after recovery."
    exit 1
fi

echo "✅ test_escalation_clean.sh PASSED: Dirty workspace cleaned and pipeline recovered."
rm -rf "$SANDBOX_DIR"
rm -f "$FLAG_FILE"
exit 0
