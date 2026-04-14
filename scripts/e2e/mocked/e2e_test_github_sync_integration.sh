#!/bin/bash
set -e
export SDLC_TEST_MODE=true

MOCK_GLOBAL="/tmp/mock_global_github"
export SDLC_GLOBAL_RUN_BASE="$MOCK_GLOBAL/.sdlc_runs"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

function setup_sandbox() {
    sandbox_dir=$(mktemp -d)
    cd "$sandbox_dir"
    git init > /dev/null 2>&1
    git config user.name "E2E Test"
    git config user.email "e2e@example.com"
    git commit --allow-empty -m "init" > /dev/null 2>&1
    echo "*.log" > .gitignore
    echo ".sdlc_repo.lock" >> .gitignore
    echo ".tmp/" >> .gitignore
    echo "scripts/__pycache__/" >> .gitignore
    echo ".github_sync_enabled" >> .gitignore
    git add .gitignore
    git commit -m "add gitignore" > /dev/null 2>&1

    RUN_DIR="$MOCK_GLOBAL/.sdlc_runs/dummy_prd"
    mkdir -p "$RUN_DIR"
    mkdir -p docs/PRDs
    echo "# Dummy PRD" > docs/PRDs/dummy_prd.md
    
    init_hermetic_sandbox "scripts"
    
    cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF
    chmod +x scripts/merge_code.py
    
    # Mock spawn_planner to create PR_001.md
    cat << 'INNER_EOF' > scripts/spawn_planner.py
import os
import sys

out_dir = None
for i, arg in enumerate(sys.argv):
    if arg == "--out-dir" or arg == "--run-dir":
        out_dir = sys.argv[i+1]
if not out_dir:
    sys.exit(1)

os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "PR_001.md"), "w") as f:
    f.write("---\nstatus: open\nslice_depth: 0\n---\nDummy PR 1")

print('{"status": "mock_success", "role": "planner"}')
sys.exit(0)
INNER_EOF
    chmod +x scripts/spawn_planner.py
    
    # Mock spawn_coder to simulate success
    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys
print("MOCK CODER RUNNING")
sys.exit(0)
INNER_EOF
    chmod +x scripts/spawn_coder.py
    
    # Mock spawn_reviewer to simulate LGTM
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys
import json

out_file = None
for i, arg in enumerate(sys.argv):
    if arg == "--out-file":
        out_file = sys.argv[i+1]

if out_file:
    with open(out_file, "w") as f:
        f.write(json.dumps({"overall_assessment": "EXCELLENT", "comments": "Mock LGTM"}))
        
print("MOCK REVIEWER RUNNING")
sys.exit(0)
INNER_EOF
    chmod +x scripts/spawn_reviewer.py
    
    # Mock openclaw to intercept github tool calls
    mkdir -p bin
    cat << 'INNER_EOF' > bin/openclaw
#!/bin/bash
if [[ "$*" == *"exec command='gh pr "* ]]; then
    # Parse out the exact command
    echo "INTERCEPTED_GH_COMMAND: $*" >> /tmp/gh_intercept.log
    exit 0
fi
exit 0
INNER_EOF
    chmod +x bin/openclaw
    export PATH="$(pwd)/bin:$PATH"
    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
}

function run_test_github_sync() {
    echo "--- Running GitHub Sync Integration Test ---"
    setup_sandbox
    rm -f /tmp/gh_intercept.log
    
    # We test the orchestrator running a full green path to see if it calls Github Sync
    # We must enable the github integration locally in config
    mkdir -p config
    echo '{"features": {"github_sync": true}}' > config/sdlc_config.json
    touch .github_sync_enabled
    git add -A
    git commit -m "clean state" > /dev/null 2>&1 || true
    python3 "$PROJECT_ROOT/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1 || true
    if [ -f "preflight.sh" ]; then chmod +x preflight.sh; fi
    git add -A
    git commit -m "doctor fix" > /dev/null 2>&1 || true
    
    python3 scripts/orchestrator.py --force-replan false --enable-exec-from-workspace --channel "test:123" --workdir "$(pwd)" --prd-file docs/PRDs/dummy_prd.md --global-dir "$MOCK_GLOBAL" --max-prs-to-process 1 > orchestrator.log 2>&1 || true

    # Did it sync to GitHub?
    if ! grep -q "MOCK_SYNC_RUN" /tmp/gh_intercept.log 2>/dev/null; then
        echo "❌ Github sync was not called despite config being true!"
        cat orchestrator.log
        exit 1
    fi
    
    echo "✅ Github Sync correctly invoked."
    rm -f /tmp/gh_intercept.log
}

function run_test_github_sync_disabled() {
    echo "--- Running GitHub Sync Disabled Test ---"
    setup_sandbox
    rm -f /tmp/gh_intercept.log
    
    # Disable github integration locally in config
    mkdir -p config
    echo '{"features": {"github_sync": false}}' > config/sdlc_config.json
    rm -f .github_sync_enabled
    git add -A
    git commit -m "clean state" > /dev/null 2>&1 || true
    python3 "$PROJECT_ROOT/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1 || true
    if [ -f "preflight.sh" ]; then chmod +x preflight.sh; fi
    git add -A
    git commit -m "doctor fix" > /dev/null 2>&1 || true
    
    python3 scripts/orchestrator.py --force-replan false --enable-exec-from-workspace --channel "test:123" --workdir "$(pwd)" --prd-file docs/PRDs/dummy_prd.md --global-dir "$MOCK_GLOBAL" --max-prs-to-process 1 > orchestrator.log 2>&1 || true

    if grep -q "MOCK_SYNC_RUN" /tmp/gh_intercept.log 2>/dev/null; then
        echo "❌ Github sync was called even though it was disabled in config!"
        exit 1
    fi
    
    echo "✅ Github Sync correctly skipped."
    rm -f /tmp/gh_intercept.log
}

rm -rf "$MOCK_GLOBAL"
run_test_github_sync
run_test_github_sync_disabled
rm -rf "$MOCK_GLOBAL"
echo "✅ All GitHub Sync Tests Passed!"
