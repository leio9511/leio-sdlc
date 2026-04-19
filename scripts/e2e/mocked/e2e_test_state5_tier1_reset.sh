#!/bin/bash
export SDLC_TEST_MODE=true
set -e

# scripts/test_state5_tier1_reset.sh - Test for State 5 Tier 1 Reset

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

function setup_sandbox() {
    sandbox_dir=$(mktemp -d)
    cd "$sandbox_dir"
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
    echo ".tmp/" >> .gitignore
    git add .gitignore
    git commit -m "add gitignore" > /dev/null 2>&1

    mkdir -p docs/PRDs
    mkdir -p scripts config

    init_hermetic_sandbox "scripts"

    echo "*.lock" >> .gitignore
    echo "scripts/__pycache__/" >> .gitignore
    git add .gitignore
    git commit -m "ignore noise" > /dev/null 2>&1
}

function run_test() {
    echo "--- Running State 5 Tier 1 Reset Test ---"
    setup_sandbox

    # Create a dummy PRD
    echo "dummy prd" > docs/PRDs/TestProject.md

    export MOCK_GLOBAL_DIR=$(mktemp -d)
    # Create a PR in the global run dir
    PROJECT_NAME=$(basename "$sandbox_dir")
    RUN_DIR="$MOCK_GLOBAL_DIR/.sdlc_runs/$PROJECT_NAME/TestProject"
    mkdir -p "$RUN_DIR"
    cat << 'INNER_EOF' > "$RUN_DIR/PR_001_Test.md"
---
status: open
---
slice_depth: 0
INNER_EOF

    # Stub spawn_coder.py to intentionally fail to trigger State 5
    cat << 'INNER_EOF' > scripts/spawn_coder.py
import sys
# Simulate a coder that leaves the workspace dirty but fails
with open("dirty_file.txt", "w") as f:
    f.write("I am dirty")
sys.exit(1)
INNER_EOF
    chmod +x scripts/spawn_coder.py

    # Stub spawn_planner.py (needed if Tier 2 is hit, but we target Tier 1)
    cat << 'INNER_EOF' > scripts/spawn_planner.py
import sys
sys.exit(0)
INNER_EOF
    chmod +x scripts/spawn_planner.py

    git add .
    git commit -m "setup test" > /dev/null 2>&1

    # Use a lock-safe execution environment
    export SDLC_BYPASS_BRANCH_CHECK=1

    # Use a mock global dir
    echo "Starting orchestrator..."
    # We use a temporary log file so we don't pollute the git status of the sandbox if it checks it
    mkdir -p "$RUN_DIR" 
    git rev-parse HEAD > "$RUN_DIR/baseline_commit.txt" 2>/dev/null || true 
    python3 scripts/orchestrator.py --global-dir "$MOCK_GLOBAL_DIR" --force-replan false --enable-exec-from-workspace --channel "valid:id" --workdir "$(pwd)" --prd-file docs/PRDs/TestProject.md --max-prs-to-process 1 --coder-session-strategy always > ../orchestrator.log 2>&1 || true
    mv ../orchestrator.log orchestrator.log

    # Assertions
    if grep -q "GitCheckoutError" orchestrator.log; then
        echo "❌ FAILED: GitCheckoutError detected in logs."
        cat orchestrator.log
        exit 1
    fi

    echo "--- Orchestrator Log Snippet ---"
    grep "Tier 1 (Reset): Deleting branch and retrying." orchestrator.log || echo "Tier 1 log not found"
    echo "-------------------------------"

    if ! grep -q "Tier 1 (Reset): Deleting branch and retrying." orchestrator.log; then
        echo "❌ FAILED: Did not reach Tier 1 Reset."
        cat orchestrator.log
        exit 1
    fi

    # Verify we are back on master (or at least the branch is gone and master is clean)
    CURRENT_BRANCH=$(git branch --show-current)
    if [ "$CURRENT_BRANCH" != "master" ]; then
        # The orchestrator might have continued to another loop or exited, 
        # but if Tier 1 worked, master should be accessible.
        git checkout master > /dev/null 2>&1 || { echo "❌ FAILED: Cannot checkout master after reset."; exit 1; }
    fi

    # Verify the global run directory structure is preserved
    PROJECT_NAME=$(basename "$sandbox_dir")
    RUN_DIR="$MOCK_GLOBAL_DIR/.sdlc_runs/$PROJECT_NAME"
    
    if [ ! -d "$RUN_DIR" ]; then
        echo "❌ FAILED: Global run directory $RUN_DIR does not exist."
        exit 1
    fi
    
    # Check that the forensic snapshot was created (proving dirty state was archived)
    SNAPSHOT_COUNT=$(ls -d "$RUN_DIR"/TestProject_crashed_* 2>/dev/null | wc -l)
    if [ "$SNAPSHOT_COUNT" -lt 1 ]; then
        echo "❌ FAILED: No forensic snapshot found."
        ls -la "$RUN_DIR" 2>/dev/null || echo "RUN_DIR does not exist"
        exit 1
    fi

    echo "✅ Found $SNAPSHOT_COUNT forensic snapshot(s)"

    # The dirty file should be in the snapshot
    if ! ls "$RUN_DIR"/TestProject_crashed_*/dirty_file.txt 2>/dev/null | head -1 | xargs -I {} test -f {}; then
        echo "❌ FAILED: dirty_file.txt not found in snapshot."
        ls -la "$RUN_DIR"/TestProject_crashed_* 2>/dev/null || echo "No snapshots"
        exit 1
    fi

    echo "✅ dirty_file.txt archived in snapshot"

    echo "✅ PASS: State 5 Tier 1 Reset successfully cleaned workspace and preserved Control Plane state."
    rm -rf "$sandbox_dir" "$MOCK_GLOBAL_DIR"
}

run_test
