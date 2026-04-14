#!/bin/bash
set -u

echo "Starting Job Queue Engine Tests..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

# Setup sandbox
SANDBOX=$(mktemp -d)
mkdir -p "$SANDBOX"

init_hermetic_sandbox "$SANDBOX/scripts"

# Teardown logic
cleanup() {
  echo "Cleaning up sandbox: $SANDBOX"
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

# Helper for asserting failure (negative tests)
assert_fail() {
  local cmd="$1"
  local expected_msg="$2"
  
  echo "Running (Expecting Failure): $cmd"
  set +e
  output=$($cmd 2>&1)
  exit_code=$?
  set -e
  
  if [ $exit_code -eq 0 ]; then
    echo "❌ FAILED: Expected command to fail with non-zero exit code, but got $exit_code."
    echo "Command: $cmd"
    echo "Output: $output"
    exit 1
  fi
  
  if [[ "$output" != *"$expected_msg"* ]]; then
    echo "❌ FAILED: Expected error message not found."
    echo "Expected substring: $expected_msg"
    echo "Actual output: $output"
    exit 1
  fi
  echo "✅ PASS: $cmd"
}

# Helper for asserting success (positive tests)
assert_success() {
  local cmd="$1"
  local expected_msg="$2"
  
  echo "Running (Expecting Success): $cmd"
  set +e
  output=$($cmd 2>&1)
  exit_code=$?
  set -e
  
  if [ $exit_code -ne 0 ]; then
    echo "❌ FAILED: Expected command to succeed but it failed (exit code $exit_code)."
    echo "Command: $cmd"
    echo "Output: $output"
    exit 1
  fi
  
  if [[ "$output" != *"$expected_msg"* ]]; then
    echo "❌ FAILED: Expected success message not found."
    echo "Expected substring: $expected_msg"
    echo "Actual output: $output"
    exit 1
  fi
  echo "✅ PASS: $cmd"
}

GET_NEXT_PR="python3 $SANDBOX/scripts/get_next_pr.py --workdir $SANDBOX"
UPDATE_PR_STATUS="python3 $SANDBOX/scripts/update_pr_status.py"

echo "--------------------------------------"
echo "Test 1: Negative - get_next_pr on missing dir"
assert_fail "$GET_NEXT_PR --job-dir $SANDBOX/missing_dir_$$" "does not exist"
echo "--------------------------------------"
echo "Test 2: Negative - update_status on missing file"
assert_fail "$UPDATE_PR_STATUS --pr-file $SANDBOX/missing_file_$$.md --status open" "[Pre-flight Failed] Cannot update status. PR file"

echo "--------------------------------------"
echo "Test 3: Negative - update_status on file without status field"
NO_STATUS_FILE="$SANDBOX/no_status.md"
echo "This file has no status field." > "$NO_STATUS_FILE"
assert_fail "$UPDATE_PR_STATUS --pr-file $NO_STATUS_FILE --status closed" "does not contain a 'status:"

echo "--------------------------------------"
echo "Test 4: Positive Flow"
JOB_DIR="$SANDBOX/feature_x"
mkdir -p "$JOB_DIR"
cat << 'EOF' > "$JOB_DIR/01_DB.md"
status: closed
EOF

cat << 'EOF' > "$JOB_DIR/02_API.md"
status: open
EOF

cat << 'EOF' > "$JOB_DIR/03_UI.md"
status: open
EOF

# Run get_next_pr.py -> expect 02_API.md
assert_success "$GET_NEXT_PR --job-dir $JOB_DIR" "02_API.md"

# Update 02_API.md to closed
assert_success "$UPDATE_PR_STATUS --pr-file $JOB_DIR/02_API.md --status closed" "[STATUS_UPDATED]"

# Run get_next_pr.py -> expect 03_UI.md
assert_success "$GET_NEXT_PR --job-dir $JOB_DIR" "03_UI.md"

# Update 03_UI.md to closed
assert_success "$UPDATE_PR_STATUS --pr-file $JOB_DIR/03_UI.md --status closed" "[STATUS_UPDATED]"

# Run get_next_pr.py -> expect queue empty
assert_success "$GET_NEXT_PR --job-dir $JOB_DIR" "[QUEUE_EMPTY]"

echo "--------------------------------------"
echo "✅ ALL TESTS PASSED!"