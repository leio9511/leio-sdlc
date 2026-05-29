#!/bin/bash
export SDLC_TEST_MODE=true
set -euo pipefail

# test_escalation_clean.sh - Verify workspace cleanup logic in State 5 Escalation

# State flag must be outside the sandbox, as the sandbox is deleted.
FLAG_FILE="/tmp/coder_failed_once.flag"
rm -f "$FLAG_FILE"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_PYTHON="$PROJECT_ROOT/scripts/dev_python.sh"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR="$(mktemp -d)"
HOME_DIR="$(mktemp -d)"
GLOBAL_DIR="/tmp/global_mock_$$"
trap 'rm -rf "$SANDBOX_DIR" "$HOME_DIR" "$GLOBAL_DIR"; rm -f "$FLAG_FILE"' EXIT

export HOME="$HOME_DIR"
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

cd "$SANDBOX_DIR"
init_git_test_sandbox "$(pwd)"

echo "initial" > init.txt
git add init.txt
git commit -m "init" > /dev/null 2>&1

mkdir -p "$GLOBAL_DIR/.sdlc_runs/$(basename "$SANDBOX_DIR")/dummy_prd"
init_hermetic_sandbox "$SANDBOX_DIR/scripts"
mkdir -p playbooks
cp "${PROJECT_ROOT}/playbooks/verifier_playbook.md" playbooks/

echo ".sdlc_run.lock" > .gitignore
echo ".sdlc_repo.lock" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.pyc" >> .gitignore
echo "*.log" >> .gitignore
echo "config/" >> .gitignore
echo ".sdlc_runs/" >> .gitignore
git add .gitignore scripts playbooks
git commit -m "setup" > /dev/null 2>&1

git rev-parse HEAD > "$GLOBAL_DIR/.sdlc_runs/$(basename "$SANDBOX_DIR")/dummy_prd/baseline_commit.txt"
cat << 'INNER_EOF' > "$GLOBAL_DIR/.sdlc_runs/$(basename "$SANDBOX_DIR")/dummy_prd/PR_001_Test.md"
---
status: open
---
slice_depth: 0
INNER_EOF

# Mock Coder: make dirty workspace and fail ONCE, then produce a real commit
cat << 'INNER_EOF' > scripts/spawn_coder.py
import os
import subprocess
import sys

flag_file = "/tmp/coder_failed_once.flag"
if not os.path.exists(flag_file):
    with open(flag_file, "w") as f:
        f.write("yes")
    # Make workspace dirty and fail
    with open("dirty_untracked.txt", "w") as f:
        f.write("dirty")
    with open("init.txt", "w") as f:
        f.write("modified")
    sys.exit(1)  # Fail the first time
else:
    # On the second run, produce a real implementation artifact and commit it.
    with open("recovered.txt", "w") as f:
        f.write("recovered")
    subprocess.run(["git", "add", "recovered.txt"], check=True)
    subprocess.run(["git", "commit", "-m", "mock recovery artifact"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(0)
INNER_EOF

cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--out-file', default='/tmp/review_report.json')
args, _ = parser.parse_known_args()
with open(args.out_file, "w") as f:
    f.write('''```json
{"overall_assessment": "EXCELLENT", "findings": []}
```
''')
INNER_EOF

cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF

cat << 'INNER_EOF' > scripts/spawn_arbitrator.py
import sys
sys.exit(1)
INNER_EOF

chmod +x scripts/spawn_coder.py scripts/spawn_reviewer.py scripts/merge_code.py scripts/spawn_arbitrator.py
git add scripts/spawn_coder.py scripts/spawn_reviewer.py scripts/merge_code.py scripts/spawn_arbitrator.py
git commit -m "pre-run clean state" > /dev/null 2>&1

echo "DEBUG: git status before orchestrator"
git status
# Run Orchestrator
export PYTHONPATH="$(pwd)/scripts:${PYTHONPATH:-}"
SDLC_BYPASS_BRANCH_CHECK=1 "$DEV_PYTHON" scripts/orchestrator.py --enable-exec-from-workspace --force-replan false --enable-exec-from-workspace --channel "valid:id" --channel "valid:id" --workdir "$(pwd)" --global-dir "$GLOBAL_DIR" --prd-file dummy_prd.md --max-prs-to-process 2 --coder-session-strategy always > orchestrator.log 2>&1 || true

# Assertions
echo "--- Orchestrator Log ---"
cat orchestrator.log
echo "-----------------------"

if [ -f "dirty_untracked.txt" ]; then
    echo "❌ test_escalation_clean.sh FAILED: dirty_untracked.txt still exists."
    exit 1
fi

MODIFIED_CONTENT="$(cat init.txt)"
if [ "$MODIFIED_CONTENT" != "initial" ]; then
    echo "❌ test_escalation_clean.sh FAILED: init.txt was not reset to its original state."
    exit 1
fi

if ! grep -q "State 5 Escalation - Tier 1 (Reset): Deleting branch and retrying." orchestrator.log; then
    echo "❌ test_escalation_clean.sh FAILED: Escalation Tier 1 was not logged."
    exit 1
fi

if ! grep -q "State 6: UAT Verification" orchestrator.log; then
    echo "❌ test_escalation_clean.sh FAILED: Orchestrator did not successfully close the PR after recovery (State 6 UAT not reached)."
    exit 1
fi

if ! grep -q "UAT Passed" orchestrator.log; then
    echo "❌ test_escalation_clean.sh FAILED: Orchestrator did not successfully pass UAT."
    exit 1
fi

echo "✅ test_escalation_clean.sh PASSED: Dirty workspace cleaned and pipeline recovered."
exit 0
