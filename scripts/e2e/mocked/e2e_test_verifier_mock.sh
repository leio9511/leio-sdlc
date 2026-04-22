#!/bin/bash
set -e

echo "Running E2E Mock Test for UAT Verifier Engine..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

# Setup temporary directories
TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT

cd "$TEST_DIR"

export SDLC_TEST_MODE="true"
export SDLC_RUN_DIR="$TEST_DIR"
export MOCK_VERIFIER_RESULT='{"status": "PASS", "executive_summary": "All requirements implemented", "verification_details": []}'

WORK_DIR="$TEST_DIR/workdir"
mkdir -p "$WORK_DIR"

init_hermetic_sandbox "$WORK_DIR/scripts"

PRD_FILE="$TEST_DIR/test_prd.md"
echo "# Mock PRD" > "$PRD_FILE"

OUT_FILE="$TEST_DIR/test_uat_report.json"

python3 "$WORK_DIR/scripts/spawn_verifier.py" --enable-exec-from-workspace --prd-files "$PRD_FILE" --workdir "$WORK_DIR" --out-file "$OUT_FILE" --enable-exec-from-workspace

if [ ! -f "$OUT_FILE" ]; then
    echo "Error: Output file $OUT_FILE was not created."
    exit 1
fi

STATUS=$(cat "$OUT_FILE" | grep '"status": "PASS"')
if [ -z "$STATUS" ]; then
    echo "Error: Output file does not contain expected mock status."
    exit 1
fi

echo "Test passed!"
exit 0
