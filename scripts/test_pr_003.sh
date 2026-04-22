#!/bin/bash
set -e

echo "--- Running PR-003 JIT Prompts & Default Engine Tests ---"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR=$(mktemp -d)
cd "$SANDBOX_DIR"

git init > /dev/null
python3 "${PROJECT_ROOT}/scripts/doctor.py" "$(pwd)" --fix > /dev/null 2>&1
git add .
git commit -m "init" > /dev/null

export PYTHONPATH="${PROJECT_ROOT}/scripts:$PYTHONPATH"

# Test Case 1: Untracked files -> git stash JIT
touch untracked_test_file
set +e
OUTPUT=$(python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --force-replan false --channel "valid:id" 2>&1)
set -e
if ! echo "$OUTPUT" | grep -q 'git stash push -m "sdlc pre-flight stash" --include-untracked'; then
    echo "❌ Test Case 1 Failed: Missing git stash JIT prompt."
    exit 1
fi
rm untracked_test_file

# Test Case 2: Uncommitted state files / outside boundaries -> commit_state.py JIT
mkdir -p docs/PRDs
touch docs/PRDs/dummy.md
git add docs/PRDs/dummy.md
set +e
OUTPUT=$(python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --force-replan false --channel "valid:id" 2>&1)
set -e
if ! echo "$OUTPUT" | grep -q 'commit_state.py'; then
    echo "❌ Test Case 2 Failed: Missing commit_state.py JIT prompt for uncommitted PRD file."
    exit 1
fi
git commit -m "add prd" > /dev/null

# Test Case 3: Default engine initialization
set +e
unset LLM_DRIVER
OUTPUT=$(python3 "${PROJECT_ROOT}/scripts/orchestrator.py" --enable-exec-from-workspace --workdir "$(pwd)" --prd-file docs/PRDs/dummy.md --force-replan false --channel "valid:id" 2>&1)
set -e
if ! echo "$OUTPUT" | grep -q 'Engine: gemini'; then
    echo "❌ Test Case 3 Failed: Engine didn't default to gemini."
    exit 1
fi

echo "✅ PR-003 Tests PASSED"
rm -rf "$SANDBOX_DIR"
exit 0
