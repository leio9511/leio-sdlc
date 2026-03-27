#!/bin/bash
set -e
export SDLC_TEST_MODE=true

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

function setup_sandbox() {
    sandbox_dir=$(mktemp -d)
    cd "$sandbox_dir"
    git init > /dev/null 2>&1
    git config user.name "E2E Test"
    git config user.email "e2e@example.com"
    git commit --allow-empty -m "init" > /dev/null 2>&1
    echo "*.log" > .gitignore
    echo ".sdlc_repo.lock" >> .gitignore
    git add .gitignore
    git commit -m "add gitignore" > /dev/null 2>&1

    mkdir -p docs/PRs/dummy_prd
    mkdir -p docs/PRDs
    echo "# Dummy PRD" > docs/PRDs/dummy_prd.md
    
    mkdir -p scripts
    cp "${PROJECT_ROOT}/scripts/orchestrator.py" scripts/
    cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
    cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
    cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/
    cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
    
    echo ".sdlc_run.lock" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
    echo "Review_Report.md" >> .gitignore
    echo "scripts/spawn_coder.py" >> .gitignore
    echo "scripts/spawn_reviewer.py" >> .gitignore
    echo "scripts/merge_code.py" >> .gitignore
    echo "scripts/get_next_pr.py" >> .gitignore
    echo "scripts/spawn_arbitrator.py" >> .gitignore
    git add .
    git commit -m "clean state" > /dev/null 2>&1
}

echo "=== Testing GitHub Sync Happy Path ==="
setup_sandbox

# Create mock PR
cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
# PR-001
INNER_EOF
git add . && git commit -m "mock PR" >/dev/null

cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys
sys.exit(0)
INNER_EOF
cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys, os
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "Looks good"}\n```')
sys.exit(0)
INNER_EOF
cat << 'INNER_EOF' > scripts/merge_code.py
import sys, subprocess, argparse
parser = argparse.ArgumentParser()
parser.add_argument("--branch", required=True)
parser.add_argument("--review-file", required=True)
parser.add_argument("--force-lgtm", action="store_true")
args, _ = parser.parse_known_args()
sys.exit(0)
INNER_EOF

# Mock the sync script in the expected global location
mkdir -p ~/.openclaw/skills/leio-github-sync/scripts
cat << 'INNER_EOF' > ~/.openclaw/skills/leio-github-sync/scripts/sync.py
import sys
print("Sync mock called")
sys.exit(0)
INNER_EOF

chmod +x ~/.openclaw/skills/leio-github-sync/scripts/sync.py

export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
SDLC_TEST_MODE=true python3 scripts/orchestrator.py --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file docs/PRDs/dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator_happy.log 2>&1 || true

if ! grep -q "Synchronizing code to GitHub..." orchestrator_happy.log; then
    echo "Happy path failed: Did not log 'Synchronizing code to GitHub...'"
    cat orchestrator_happy.log
    exit 1
fi

if ! grep -q "GitHub sync complete." orchestrator_happy.log; then
    echo "Happy path failed: Did not log 'GitHub sync complete.'"
    cat orchestrator_happy.log
    exit 1
fi
echo "✅ Happy path passed."


echo "=== Testing GitHub Sync Failure Path ==="
setup_sandbox

# Create mock PR
cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
# PR-001
INNER_EOF
git add . && git commit -m "mock PR" >/dev/null

cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys
sys.exit(0)
INNER_EOF
cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys, os
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "Looks good"}\n```')
sys.exit(0)
INNER_EOF
cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF

# Mock the sync script to fail
cat << 'INNER_EOF' > ~/.openclaw/skills/leio-github-sync/scripts/sync.py
import sys
print("Simulating sync failure", file=sys.stderr)
sys.exit(1)
INNER_EOF

chmod +x ~/.openclaw/skills/leio-github-sync/scripts/sync.py

export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
SDLC_TEST_MODE=true python3 scripts/orchestrator.py --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file docs/PRDs/dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator_fail.log 2>&1 || true

if ! grep -q "Synchronizing code to GitHub..." orchestrator_fail.log; then
    echo "Failure path failed: Did not log 'Synchronizing code to GitHub...'"
    cat orchestrator_fail.log
    exit 1
fi

if ! grep -q "GitHub Sync failed" orchestrator_fail.log; then
    echo "Failure path failed: Did not log warning about sync failure"
    cat orchestrator_fail.log
    exit 1
fi

if ! grep -q "successfully merged to master." orchestrator_fail.log; then
    echo "Failure path failed: Orchestrator did not complete successfully"
    cat orchestrator_fail.log
    exit 1
fi
echo "✅ Failure path passed."

rm -rf ~/.openclaw/skills/leio-github-sync/scripts/sync.py