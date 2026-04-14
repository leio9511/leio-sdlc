#!/bin/bash
set -e

echo "Running E2E Mock Test for Orchestrator UAT Integration..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT
cd "$TEST_DIR"

export SDLC_TEST_MODE="true"
export SDLC_RUN_DIR="$TEST_DIR"
export SDLC_BYPASS_BRANCH_CHECK="1"
export OPENCLAW_SESSION_KEY="mock:channel"

WORK_DIR="$TEST_DIR/workdir"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
git init >/dev/null 2>&1
git commit --allow-empty -m "Initial" >/dev/null 2>&1

# Initialize hermetic sandbox with all required scripts
init_hermetic_sandbox "$WORK_DIR/scripts"
init_hermetic_sandbox "$TEST_DIR/scripts"

# Create a minimal config directory
mkdir -p "$TEST_DIR/config"
cp -r "$PROJECT_ROOT/config/"* "$TEST_DIR/config/" 2>/dev/null || true

# Create preflight.sh
mkdir -p "$WORK_DIR/scripts"
echo "#!/bin/bash" > "$WORK_DIR/scripts/preflight.sh"
echo "exit 0" >> "$WORK_DIR/scripts/preflight.sh"
chmod +x "$WORK_DIR/scripts/preflight.sh"

# Create a PRD file
PRD_FILE="$WORK_DIR/test_prd.md"
cat << 'EOF' > "$PRD_FILE"
# Mock PRD
## 1. Context & Problem
## 2. Requirements & User Stories
## 3. Architecture & Technical Strategy
## 4. Acceptance Criteria
## 5. Overall Test Strategy
## 6. Framework Modifications
## 7. Hardcoded Content
EOF

# Add .sdlc_runs and lock file to .gitignore before running orchestrator
echo ".sdlc_runs/" >> "$WORK_DIR/.gitignore"
echo ".sdlc_repo.lock" >> "$WORK_DIR/.gitignore"
echo ".tmp/" >> "$WORK_DIR/.gitignore"

git add -A >/dev/null 2>&1 || true
git commit -m "setup test" >/dev/null 2>&1 || true

ORCHESTRATOR="$TEST_DIR/scripts/orchestrator.py"

echo "Test Case 1: Handle Missing/Invalid JSON gracefully"
export MOCK_VERIFIER_RESULT='invalid json'

# Force empty queue so orchestrator enters state 6 directly
mkdir -p "$WORK_DIR/.sdlc_runs/workdir/test_prd"
touch "$WORK_DIR/.sdlc_runs/workdir/test_prd/.queue_empty_force"

# Clean workspace before orchestrator runs
git reset --hard HEAD >/dev/null 2>&1
git clean -fd >/dev/null 2>&1

echo "DEBUG: git status before orchestrator:"
git status --porcelain

OUT=$(python3 "$ORCHESTRATOR" --max-prs-to-process 0 --workdir "$WORK_DIR" --prd-file "$PRD_FILE" --force-replan false --enable-exec-from-workspace 2>&1 || true)

echo "DEBUG: git status after orchestrator:"
git status --porcelain

if [[ "$OUT" != *"[ACTION REQUIRED FOR MANAGER] UAT Failed. uat_report.json is missing or invalid JSON."* ]]; then
    echo "Fail Test Case 1: Did not print safe error message for invalid json"
    echo "$OUT"
    exit 1
fi
echo "Passed Test Case 1"

echo "Test Case 2: SUCCESS_HANDOFF when PASS"
export MOCK_VERIFIER_RESULT='{"status": "PASS", "executive_summary": "Mock passed", "verification_details": []}'

# Clean workspace between tests
git reset --hard HEAD >/dev/null 2>&1
git clean -fd >/dev/null 2>&1

OUT=$(python3 "$ORCHESTRATOR" --debug --max-prs-to-process 0 --workdir "$WORK_DIR" --prd-file "$PRD_FILE" --force-replan false --enable-exec-from-workspace 2>&1 || true)
if [[ "$OUT" != *"[SUCCESS_HANDOFF] UAT Passed. You are authorized to close the ticket using issues.py."* ]]; then
    echo "Fail Test Case 2: Did not print SUCCESS_HANDOFF"
    echo "$OUT"
    exit 1
fi
echo "Passed Test Case 2"

echo "Test Case 3: ACTION REQUIRED when NEEDS_FIX"
export MOCK_VERIFIER_RESULT='{"status": "NEEDS_FIX", "executive_summary": "Mock failed", "verification_details": []}'

# Clean workspace between tests
git reset --hard HEAD >/dev/null 2>&1
git clean -fd >/dev/null 2>&1

OUT=$(python3 "$ORCHESTRATOR" --max-prs-to-process 0 --workdir "$WORK_DIR" --prd-file "$PRD_FILE" --force-replan false --enable-exec-from-workspace 2>&1 || true)
if [[ "$OUT" != *"[ACTION REQUIRED FOR MANAGER] UAT Failed. Read uat_report.json, summarize the MISSING items to the Boss, and ask whether to append a hotfix or redo."* ]]; then
    echo "Fail Test Case 3: Did not print ACTION REQUIRED FOR MANAGER"
    echo "$OUT"
    exit 1
fi
echo "Passed Test Case 3"

echo "All tests passed!"
exit 0
