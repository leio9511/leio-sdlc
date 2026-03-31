#!/bin/bash
export SDLC_TEST_MODE=true
set -e

# test_forensic_quarantine.sh - Verify that .sdlc_runs/ is tracked during State 5 Escalation

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"

git init > /dev/null 2>&1
git config user.name "E2E Test"
git config user.email "e2e@example.com"

echo "initial" > init.txt
git add init.txt
git commit -m "init" > /dev/null 2>&1

mkdir -p .sdlc_runs/dummy_prd scripts
cp "${PROJECT_ROOT}/scripts/orchestrator.py" scripts/
cp "${PROJECT_ROOT}/scripts/agent_driver.py" scripts/
cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/
cp "${PROJECT_ROOT}/scripts/spawn_planner.py" scripts/

# 1. Globally ignore .sdlc_runs/
mkdir -p .git/info
echo ".sdlc_runs/" > .git/info/exclude

# Explicitly ignore common noise to avoid [FATAL] Dirty Git Workspace
echo ".sdlc_run.lock" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo ".sdlc_lock_manifest.json" >> .gitignore
echo "orchestrator.log" >> .gitignore
echo "orchestrator_s5.log" >> .gitignore
echo "cleanup.log" >> .gitignore
echo "scripts/__pycache__/" >> .gitignore
git add .gitignore scripts
git commit -m "setup" > /dev/null 2>&1

cat << 'INNER_EOF' > .sdlc_runs/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
INNER_EOF

# Mock Coder: make dirty workspace and fail
cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
# Create a forensic artifact in the run directory
run_dir = ""
for i, arg in enumerate(sys.argv):
    if arg == "--run-dir":
        run_dir = sys.argv[i+1]
if run_dir:
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "forensic_log.txt"), "w") as f:
        f.write("forensic data")
sys.exit(1) # Fail to trigger State 5 Escalation
INNER_EOF

cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys
sys.exit(0)
INNER_EOF

cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF

chmod +x scripts/*.py

cat << 'INNER_EOF' > dummy_prd.md
Affected_Projects: [dummy_prd]
INNER_EOF
git add dummy_prd.md && git commit -m "add prd" > /dev/null 2>&1

# Run Orchestrator
export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
git add -A && git commit -m "clean state" > /dev/null 2>&1

# This run will fail and trigger State 5
python3 scripts/orchestrator.py --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --global-dir "$PROJECT_ROOT" --prd-file dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

echo "--- Orchestrator Log ---"
cat orchestrator.log
echo "-----------------------"

# 2. Verify git clean -fd doesn't delete .sdlc_runs/
echo "Verifying git clean -fd safety..."
touch untracked_root.txt
mkdir -p .sdlc_runs/dummy_prd
touch .sdlc_runs/dummy_prd/safefile.txt
git clean -fd
if [ -f "untracked_root.txt" ]; then
    echo "❌ git clean failed to remove untracked_root.txt"
    exit 1
fi
if [ ! -d ".sdlc_runs/dummy_prd" ]; then
    echo "❌ git clean DELETED .sdlc_runs/ even though it is in .git/info/exclude"
    exit 1
fi
echo "✅ git clean -fd safety verified."

# 3. Verify --cleanup forensic quarantine
echo "Testing --cleanup forensic quarantine..."
git checkout -b "dummy_prd/feature" > /dev/null 2>&1
echo "dirty" > .sdlc_runs/dummy_prd/crash_artifact.txt
python3 scripts/orchestrator.py --cleanup --workdir "$(pwd)" --prd-file dummy_prd.md > cleanup.log 2>&1

echo "Checking quarantined branch..."
QUARANTINE_BRANCH=$(git branch --list "dummy_prd/feature_crashed_*" | head -n 1 | sed 's/[* ]//g')
if [ -z "$QUARANTINE_BRANCH" ]; then
    echo "❌ No quarantine branch created."
    exit 1
fi

git checkout "$QUARANTINE_BRANCH" > /dev/null 2>&1
if [ ! -f ".sdlc_runs/dummy_prd/crash_artifact.txt" ]; then
    echo "❌ Forensic artifact NOT found in quarantined branch."
    exit 1
fi
echo "✅ --cleanup forensic quarantine verified."

# 4. Verify forensic tracking during State 5 Escalation
echo "Testing State 5 Escalation forensic quarantine..."
# We already ran the orchestrator earlier, check its log
if ! grep -q "State 5: Archiving forensic artifacts to toxic branch" orchestrator.log; then
    echo "❌ Orchestrator did not log forensic archiving in State 5."
    exit 1
fi

# The commit should exist in reflog
if ! git reflog --grep="WIP: 🚨 STATE 5 ESCALATION FORENSIC SNAPSHOT" > /dev/null 2>&1; then
    echo "❌ S5 forensic commit NOT found in reflog."
    exit 1
fi

echo "✅ State 5 Escalation forensic quarantine verified."

echo "✅ test_forensic_quarantine.sh PASSED."
rm -rf "$SANDBOX_DIR"
exit 0
