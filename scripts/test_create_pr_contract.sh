#!/bin/bash
set -e

echo "Running test_create_pr_contract.sh..."

WORK_DIR="$(pwd)/.test_tmp"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

# Initialize a git repo to test tracking
cd "$WORK_DIR"
git init > /dev/null 2>&1
cd - > /dev/null 2>&1

TEST_DIR="$WORK_DIR/test_queue_dir"
mkdir -p "$TEST_DIR"

CONTENT_FILE="$WORK_DIR/test_content.txt"
echo "Test PR content" > "$CONTENT_FILE"

SCRIPT_PATH="$(dirname "$0")/create_pr_contract.py"

# Negative: Missing content file
if python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Fail" --content-file "$WORK_DIR/non_existent.txt" 2>/dev/null; then
  echo "❌ Expected failure for missing content file, but it succeeded."
  exit 1
fi

# Positive 1: First PR
OUTPUT1=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "First PR" --content-file "$CONTENT_FILE")
echo "$OUTPUT1" | grep -q "\[PR_CREATED\]" || { echo "❌ Expected [PR_CREATED] output"; exit 1; }
FILE1=$(echo "$OUTPUT1" | awk '{print $2}')
if [[ "$FILE1" != *"/PR_001_First_PR.md" ]]; then echo "❌ Wrong filename: $FILE1"; exit 1; fi
# status: open is no longer injected by this script, but expected from template

# Positive 2: Second PR
OUTPUT2=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Second PR" --content-file "$CONTENT_FILE")
FILE2=$(echo "$OUTPUT2" | awk '{print $2}')
if [[ "$FILE2" != *"/PR_002_Second_PR.md" ]]; then echo "❌ Wrong filename: $FILE2"; exit 1; fi

# Positive 3: Insert after 001
OUTPUT3=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Insert One" --content-file "$CONTENT_FILE" --insert-after "001")
FILE3=$(echo "$OUTPUT3" | awk '{print $2}')
if [[ "$FILE3" != *"/PR_001_1_Insert_One.md" ]]; then echo "❌ Wrong filename for insert: $FILE3"; exit 1; fi

# Positive 4: Insert after 001 again
OUTPUT4=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Insert Two" --content-file "$CONTENT_FILE" --insert-after "001")
FILE4=$(echo "$OUTPUT4" | awk '{print $2}')
if [[ "$FILE4" != *"/PR_001_2_Insert_Two.md" ]]; then echo "❌ Wrong filename for second insert: $FILE4"; exit 1; fi

# Positive 5: Third PR normal
OUTPUT5=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Third PR" --content-file "$CONTENT_FILE")
FILE5=$(echo "$OUTPUT5" | awk '{print $2}')
if [[ "$FILE5" != *"/PR_003_Third_PR.md" ]]; then echo "❌ Wrong filename: $FILE5"; exit 1; fi

# Positive 6: With project parameter (deprecated/ignored)
OUTPUT6=$(python3 "$SCRIPT_PATH" --workdir "$WORK_DIR" --job-dir "$TEST_DIR" --title "Project PR" --content-file "$CONTENT_FILE" --project "leio-sdlc")
echo "$OUTPUT6" | grep -q "\[PR_CREATED\]" || { echo "❌ Expected [PR_CREATED] output with --project"; exit 1; }
FILE6=$(echo "$OUTPUT6" | awk '{print $2}')
if [[ "$FILE6" != *"/PR_004_Project_PR.md" ]]; then echo "❌ Wrong filename for project test: $FILE6"; exit 1; fi

# Check Git tracking (Ensure NO git add was performed)
cd "$WORK_DIR"
UNTRACKED=$(git ls-files --others --exclude-standard)
if ! echo "$UNTRACKED" | grep -q "test_queue_dir/PR_001_First_PR.md"; then
  echo "❌ Error: PR_001_First_PR.md is not untracked. It was likely staged by the script."
  exit 1
fi
STAGED=$(git ls-files --cached)
if echo "$STAGED" | grep -q "test_queue_dir/PR_001_First_PR.md"; then
  echo "❌ Error: PR_001_First_PR.md was staged in git index."
  exit 1
fi
cd - > /dev/null 2>&1

echo "✅ test_create_pr_contract.sh PASSED"
