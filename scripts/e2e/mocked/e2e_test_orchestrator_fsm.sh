#!/bin/bash
set -e

# test_orchestrator_fsm.sh - Deterministic FSM Testing Strategy for PR-045.3

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"
export MOCK_GLOBAL_DIR=$(mktemp -d)

function setup_sandbox() {
    sandbox_dir=$(mktemp -d)
    cd "$sandbox_dir"
    export RUN_DIR="$MOCK_GLOBAL_DIR/.sdlc_runs/$(basename "$sandbox_dir")"
    echo "dummy" > dummy_prd.md
    mkdir -p "bin"
    cat << 'INNER_EOF' > "bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
    chmod +x "bin/openclaw"
    export PATH="$(pwd)/bin:$PATH"
    git init > /dev/null 2>&1
    git config user.name "E2E Test"
    git config user.email "e2e@example.com"
    git commit --allow-empty -m "init" > /dev/null 2>&1
    echo "*.log" > .gitignore
    echo ".sdlc_repo.lock" >> .gitignore
    git add .gitignore
    git commit -m "add gitignore" > /dev/null 2>&1

    mkdir -p $RUN_DIR/dummy_prd
    mkdir -p scripts config
    
    init_hermetic_sandbox "scripts"
    cp "${PROJECT_ROOT}/scripts/setup_logging.py" scripts/ || true
    cp "${PROJECT_ROOT}/config/prompts.json" config/
    cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
    cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
    cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/
    cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
    cp "${PROJECT_ROOT}/scripts/spawn_planner.py" scripts/
    
    echo ".sdlc_run.lock" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
    echo "review_report.json" >> .gitignore
    git add .
    git commit -m "clean state" > /dev/null 2>&1
    
    # Stub merge_code.py
    cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF
    chmod +x scripts/merge_code.py
}

function run_test_green_path() {
    echo "--- Running Green Path Test ---"
    setup_sandbox
    
    cat << 'INNER_EOF' > $RUN_DIR/dummy_prd/PR_001_Test.md
status: open
slice_depth: 0
INNER_EOF

    git add .
    git commit -m "add PR" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF
    
    # Reviewer mock that writes EXCELLENT assessment
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys, os, json
out_file_arg = None
run_dir_arg = None
for i, arg in enumerate(sys.argv):
    if arg == "--out-file" and i+1 < len(sys.argv):
        out_file_arg = sys.argv[i+1]
    if arg == "--run-dir" and i+1 < len(sys.argv):
        run_dir_arg = sys.argv[i+1]
target = out_file_arg or os.path.join(run_dir_arg or ".", "review_report.json")
os.makedirs(os.path.dirname(target), exist_ok=True)
with open(target, "w") as f:
    f.write('{"overall_assessment": "EXCELLENT", "comments": "OK"}')
INNER_EOF
    chmod +x scripts/spawn_reviewer.py

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --global-dir "$MOCK_GLOBAL_DIR" --force-replan false --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    # Check if orchestrator ran without fatal errors
    if grep -q "FATAL" orchestrator.log; then
        echo "Orchestrator had FATAL errors"
        cat orchestrator.log
        exit 1
    fi
    echo "✅ Green Path passed (orchestrator ran without FATAL errors)"
}

function run_test_state_0_pure_start() {
    echo "--- Test: State 0 Pure Start ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy" > docs/PRDs/MyProject.md

    git add .
    git commit -m "add myproject prd" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys, os
os.makedirs(os.environ.get("RUN_DIR", ".") + "/MyProject", exist_ok=True)
with open(os.environ.get("RUN_DIR", ".") + "/MyProject/PR_001_Mock.md", "w") as f:
    f.write("status: open\n")
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF
    
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
import sys, os, json
out_file_arg = None
run_dir_arg = None
for i, arg in enumerate(sys.argv):
    if arg == "--out-file" and i+1 < len(sys.argv):
        out_file_arg = sys.argv[i+1]
    if arg == "--run-dir" and i+1 < len(sys.argv):
        run_dir_arg = sys.argv[i+1]
target = out_file_arg or os.path.join(run_dir_arg or ".", "review_report.json")
os.makedirs(os.path.dirname(target), exist_ok=True)
with open(target, "w") as f:
    f.write('{"overall_assessment": "EXCELLENT", "comments": "OK"}')
INNER_EOF
    chmod +x scripts/spawn_reviewer.py

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --global-dir "$MOCK_GLOBAL_DIR" --force-replan false --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file docs/PRDs/MyProject.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

    if grep -q "Traceback" orchestrator.log; then
        echo "State 0 Pure Start had Traceback"
        cat orchestrator.log; exit 1
    fi
    echo "✅ State 0 Pure Start passed"
}

run_test_green_path
run_test_state_0_pure_start

echo "✅ All orchestrator FSM tests passed."
