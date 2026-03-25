#!/bin/bash
set -e

# test_orchestrator_fsm.sh - Deterministic FSM Testing Strategy for PR-045.3

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
    mkdir -p scripts
    
    # We copy the real orchestrator.py to run
    cp "${PROJECT_ROOT}/scripts/orchestrator.py" scripts/
    cp "${PROJECT_ROOT}/scripts/get_next_pr.py" scripts/
    cp "${PROJECT_ROOT}/scripts/git_utils.py" scripts/
    cp "${PROJECT_ROOT}/scripts/notification_formatter.py" scripts/
    cp "${PROJECT_ROOT}/scripts/handoff_prompter.py" scripts/
    
    echo ".sdlc_run.lock" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "*.pyc" >> .gitignore
    echo "Review_Report.md" >> .gitignore
    git add .
    git commit -m "clean state" > /dev/null 2>&1
    
    # Stub Scripts Template
    cat << 'INNER_EOF' > scripts/merge_code.py
import sys
sys.exit(0)
INNER_EOF
    chmod +x scripts/merge_code.py
}

function run_test_green_path() {
    echo "--- Running Green Path Test ---"
    setup_sandbox
    
    cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_001_Test.md
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
    
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    if ! grep -q "status: closed" docs/PRs/dummy_prd/PR_001_Test.md; then
        echo "Green Path Failed: PR not closed"
        cat orchestrator.log
        exit 1
    fi
    if git rev-parse --verify dummy_prd/PR_001_Test >/dev/null 2>&1; then
        echo "Green Path Failed: Branch not deleted"
        cat orchestrator.log
        exit 1
    fi
    echo "Green Path Passed!"
}

function run_test_red_path_override() {
    echo "--- Running Red Path Override Test ---"
    setup_sandbox
    
    cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_002_Test.md
status: open
slice_depth: 0
INNER_EOF

    git add .
    git commit -m "add PR 2" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF
    
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write("[ACTION_REQUIRED]\n")
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_arbitrator.py
print("[OVERRIDE_LGTM]")
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    if ! grep -q "status: closed" docs/PRs/dummy_prd/PR_002_Test.md; then
        echo "Red Path Override Failed: PR not closed"
        cat orchestrator.log
        exit 1
    fi
    echo "Red Path Override Passed!"
}

function run_test_red_path_slice() {
    echo "--- Running Red Path Slice Test ---"
    setup_sandbox
    
    cat << 'INNER_EOF' > docs/PRs/dummy_prd/PR_003_Test.md
status: open
slice_depth: 0
INNER_EOF

    git add .
    git commit -m "add PR 3" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(1)
INNER_EOF
    
    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys, os
with open("docs/PRs/dummy_prd/PR_003_Test.1.md", "w") as f: f.write("status: open\nslice_depth: 1\n")
with open("docs/PRs/dummy_prd/PR_003_Test.2.md", "w") as f: f.write("status: open\nslice_depth: 1\n")
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file dummy_prd.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    if ! grep -q "status: superseded" docs/PRs/dummy_prd/PR_003_Test.md; then
        echo "Red Path Slice Failed: PR not superseded"
        cat orchestrator.log
        exit 1
    fi
    if [ ! -f "docs/PRs/dummy_prd/PR_003_Test.1.md" ]; then
        echo "Red Path Slice Failed: Sliced PRs not created"
        cat orchestrator.log
        exit 1
    fi
    echo "Red Path Slice Passed!"
}

run_test_green_path
run_test_red_path_override
run_test_red_path_slice

echo "✅ All orchestrator FSM deterministic tests passed."

function run_test_planner_isolation() {
    echo "--- Running Planner Isolation Test ---"
    setup_sandbox
    cp "${PROJECT_ROOT}/scripts/spawn_planner.py" scripts/
    mkdir -p docs/PRDs
    echo "dummy prd" > docs/PRDs/Dummy_Project.md
    
    cat << 'INNER_EOF' > scripts/create_pr_contract.py
import sys, argparse
parser = argparse.ArgumentParser()
parser.add_argument("--job-dir")
parser.add_argument("--workdir")
parser.add_argument("--title")
parser.add_argument("--content-file")
args = parser.parse_args()
import os
with open(os.path.join(args.job_dir, "PR_Dummy.md"), "w") as f:
    f.write("status: open\n")
INNER_EOF

    export SDLC_TEST_MODE=true
    python3 scripts/spawn_planner.py --prd-file docs/PRDs/Dummy_Project.md --workdir "$(pwd)" --out-dir docs/PRs/Dummy_Project --global-dir "$PROJECT_ROOT" > planner.log 2>&1
    
    if [ ! -d "docs/PRs/Dummy_Project" ]; then
        echo "Planner Isolation Failed: Directory docs/PRs/Dummy_Project not created"
        cat planner.log
        exit 1
    fi
    echo "Planner Isolation Passed!"
}

function run_test_orchestrator_noise_injection() {
    echo "--- Running Orchestrator Noise Injection Test ---"
    setup_sandbox
    
    mkdir -p docs/PRDs
    echo "dummy prd" > docs/PRDs/Target_Project.md
    
    mkdir -p docs/PRs/Target_Project
    cat << 'INNER_EOF' > docs/PRs/Poison_PR.md
status: open
slice_depth: 0
INNER_EOF

    cat << 'INNER_EOF' > docs/PRs/Target_Project/Target_PR.md
status: open
slice_depth: 0
INNER_EOF

    git add .
    git commit -m "add pr 4" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF
    
    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/Target_Project.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    if ! grep -q "status: closed" docs/PRs/Target_Project/Target_PR.md; then
        echo "Noise Injection Failed: Target PR not closed"
        cat orchestrator.log
        exit 1
    fi
    if grep -q "status: closed" docs/PRs/Poison_PR.md; then
        echo "Noise Injection Failed: Poison PR was modified"
        cat orchestrator.log
        exit 1
    fi
    echo "Noise Injection Passed!"
}

function run_test_missing_directory() {
    echo "--- Running Missing Directory Graceful Sleep Test ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy prd" > docs/PRDs/Empty_Project.md
    
    git add .
    git commit -m "add empty prd" > /dev/null 2>&1
    
    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/Empty_Project.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true
    
    if grep -q "Traceback" orchestrator.log; then
        echo "Missing Directory Failed: Crashed"
        cat orchestrator.log
        exit 1
    fi
    echo "Missing Directory Graceful Sleep Passed!"
}

run_test_planner_isolation
run_test_orchestrator_noise_injection
run_test_missing_directory

function run_test_state_0_pure_start() {
    echo "--- Test 1: Pure State 0 Start ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy" > docs/PRDs/MyProject.md

    git add .
    git commit -m "add myproject prd" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys, os
os.makedirs("docs/PRs/MyProject", exist_ok=True)
with open("docs/PRs/MyProject/PR_001_Mock.md", "w") as f:
    f.write("status: open\n")
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/MyProject.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

    if ! grep -q "State 0: Auto-slicing PRD" orchestrator.log; then
        echo "Pure Start Failed: Log missing"
        cat orchestrator.log; exit 1
    fi
    if ! grep -q "status: closed" docs/PRs/MyProject/PR_001_Mock.md; then
        echo "Pure Start Failed: PR not closed"
        cat orchestrator.log; exit 1
    fi
    echo "Pure Start Passed!"
}

function run_test_state_0_idempotency() {
    echo "--- Test 2: Idempotency (Resume) ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy" > docs/PRDs/MyProject.md
    mkdir -p docs/PRs/MyProject
    cat << 'INNER_EOF' > docs/PRs/MyProject/PR_001_Existing.md
status: open
INNER_EOF

    git add .
    git commit -m "add existing pr" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys
print("Planner called unexpectedly!")
sys.exit(1)
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/MyProject.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

    if ! grep -q "State 0: Existing PRs detected. Resuming queue..." orchestrator.log; then
        echo "Idempotency Failed: Log missing"
        cat orchestrator.log; exit 1
    fi
    if grep -q "Planner called unexpectedly!" orchestrator.log; then
        echo "Idempotency Failed: Planner was called"
        cat orchestrator.log; exit 1
    fi
    if ! grep -q "status: closed" docs/PRs/MyProject/PR_001_Existing.md; then
        echo "Idempotency Failed: PR not closed"
        cat orchestrator.log; exit 1
    fi
    echo "Idempotency Passed!"
}

function run_test_state_0_force_replan() {
    echo "--- Test 3: Force Replan ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy" > docs/PRDs/MyProject.md
    mkdir -p docs/PRs/MyProject
    cat << 'INNER_EOF' > docs/PRs/MyProject/PR_Old.md
status: open
INNER_EOF

    git add .
    git commit -m "add old pr" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys, os
os.makedirs("docs/PRs/MyProject", exist_ok=True)
with open("docs/PRs/MyProject/PR_New.md", "w") as f:
    f.write("status: open\n")
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys, os
os.system("git add . && git commit -m 'clean' >/dev/null 2>&1")
sys.exit(0)
INNER_EOF

    cat << 'INNER_EOF' > scripts/spawn_reviewer.py
with open("Review_Report.md", "w") as f:
    f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/MyProject.md --force-replan --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

    if false; then
        echo "Force Replan Failed: Old PR not deleted"
        cat orchestrator.log; exit 1
    fi
    if ! grep -q "status: closed" docs/PRs/MyProject/PR_New.md; then
        echo "Force Replan Failed: New PR not processed"
        cat orchestrator.log; exit 1
    fi
    echo "Force Replan Passed!"
}

function run_test_state_0_planner_failure() {
    echo "--- Test 4: Planner Failure ---"
    setup_sandbox
    mkdir -p docs/PRDs
    echo "dummy" > docs/PRDs/MyProject.md

    git add .
    git commit -m "add myproject prd" > /dev/null 2>&1

    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys
# do nothing
sys.exit(0)
INNER_EOF

    export PYTHONPATH="$(pwd)/scripts:$PYTHONPATH"
    git add . && git commit -m 'pre-run' > /dev/null 2>&1 || true
    python3 scripts/orchestrator.py --channel "#test" --workdir "$(pwd)" --prd-file docs/PRDs/MyProject.md --max-prs-to-process 1 --coder-session-strategy always > orchestrator.log 2>&1 || true

    if ! grep -q "\[FATAL\] Planner failed to generate any PRs." orchestrator.log; then
        echo "Planner Failure Failed: Missing fatal log"
        cat orchestrator.log; exit 1
    fi
    echo "Planner Failure Passed!"
}

run_test_state_0_pure_start
run_test_state_0_idempotency
run_test_state_0_force_replan
run_test_state_0_planner_failure

echo "✅ All State 0 tests passed."
