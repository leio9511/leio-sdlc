#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

DIR="/tmp/test_072_workspace_$$"
mkdir -p "$DIR/docs/PRs/mock_072"

cat << 'FILEEOF' > "$DIR/docs/PRs/mock_072/PR_001_Mock.md"
---
status: closed
---

# PR-001
This PR fixes the `status: open` bug.
The previous system falsely detected the text "status: open" in this sentence!
FILEEOF

echo "Running Assertion 1..."
cd "$DIR"
OUTPUT=$(python3 "$PROJECT_DIR/scripts/get_next_pr.py" --workdir . --job-dir docs/PRs/mock_072)

if echo "$OUTPUT" | grep -q "QUEUE_EMPTY"; then
    echo "Assertion 1 passed."
else
    echo "Assertion 1 failed. Output was: $OUTPUT"
    exit 1
fi

echo "Running Assertion 2..."
python3 "$PROJECT_DIR/scripts/update_pr_status.py" --pr-file "$DIR/docs/PRs/mock_072/PR_001_Mock.md" --status in_progress

HEAD_LINE=$(head -n 2 "$DIR/docs/PRs/mock_072/PR_001_Mock.md" | tail -n 1)
if [ "$HEAD_LINE" != "status: in_progress" ]; then
    echo "Assertion 2 failed. Status line is: $HEAD_LINE"
    exit 1
fi

BODY_LINE=$(grep "This PR fixes the \`status: open\` bug." "$DIR/docs/PRs/mock_072/PR_001_Mock.md")
if [ -z "$BODY_LINE" ]; then
    echo "Assertion 2 failed. Body 'status: open' was modified."
    exit 1
fi

echo "Assertion 2 passed."
rm -rf "$DIR"
exit 0
