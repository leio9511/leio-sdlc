#!/bin/bash
set -e

echo "Setting up Planner Triad Test..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

cd "$TEST_DIR"
init_hermetic_sandbox "$TEST_DIR/scripts"

mkdir -p docs/PRDs
cat << 'EOF' > docs/PRDs/dummy_triad_prd.md
# Dummy PRD for Planner Triad Test
Identifier: PL-999
Please generate a PR document based on this PRD. Make sure to include the identifier PL-999 and markdown headers.
EOF

unset SDLC_TEST_MODE

echo "Running Planner..."
python3 scripts/spawn_planner.py --prd-file docs/PRDs/dummy_triad_prd.md --workdir "$(pwd)" --global-dir "$(pwd)" > triad_planner.log 2>&1 || true

echo "Asserting Output..."
cat triad_planner.log
# Find the generated PR file
PR_FILE=$( (ls .sdlc_runs/*/dummy_triad_prd/PR_Slice_1.md 2>/dev/null || ls .sdlc_runs/*/dummy_triad_prd/PR_A.md 2>/dev/null || ls .sdlc_runs/*/dummy_triad_prd/PR_001_*.md 2>/dev/null) | head -n 1 || true)

if [ -n "$PR_FILE" ] && [ -f "$PR_FILE" ]; then
    if grep -q "PL-999" "$PR_FILE" && grep -q "#" "$PR_FILE"; then
        echo "✅ Planner Triad Test Passed."
        exit 0
    else
        echo "❌ Planner Triad Test Failed. Content check failed."
        cat "$PR_FILE"
        exit 1
    fi
else
    echo "❌ Planner Triad Test Failed. PR file not found."
    exit 1
fi
