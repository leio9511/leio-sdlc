#!/bin/bash
set -e

echo "Setting up Triad Consistency Test for Reviewer..."

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT

cd "$TEST_DIR"
init_hermetic_sandbox "$TEST_DIR/scripts"

# 2.2.1 Prepare Dummy Files
mkdir -p tests
cat << 'EOF' > tests/dummy_triad_pr.md
# Dummy PR
This is a test PR. Please output an APPROVED status in JSON.
EOF

cat << 'EOF' > tests/dummy_triad.diff
--- a/tests/dummy_script.py
+++ b/tests/dummy_script.py
@@ -1,2 +1,3 @@
 def test_func():
-    return False
+    return True
EOF

# 2.2.2 Environment Configuration
unset SDLC_TEST_MODE

# 2.2.3 Execute Test and Capture Logs
echo "Executing Reviewer spawn script..."
# Pass mandatory --global-dir
python3 scripts/spawn_reviewer.py --pr-file tests/dummy_triad_pr.md --diff-target HEAD --override-diff-file tests/dummy_triad.diff --workdir "$(pwd)" --global-dir "$(pwd)" --out-file review_report.json > triad_reviewer.log 2>&1 || true

# 2.2.4 Assertions
echo "Running assertions..."
if ! grep -q '"overall_assessment": "EXCELLENT"' review_report.json && ! grep -q '"overall_assessment": "ACCEPTABLE"' review_report.json; then
    # Sometimes it might just output APPROVED in status or overall_assessment
    if ! grep -q -i "approved" review_report.json && ! grep -q -i '"overall_assessment": "EXCELLENT"' review_report.json; then
        echo "❌ ERROR: Missing APPROVED status in report."
        cat review_report.json
        exit 1
    fi
fi

if grep -q -- "--- a/" triad_reviewer.log; then
    echo "❌ ERROR: Output contains raw diff '--- a/'."
    cat triad_reviewer.log
    exit 1
fi

echo "✅ All assertions passed! Test successful."
exit 0
