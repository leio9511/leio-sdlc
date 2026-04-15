#!/bin/bash
set -e

echo "--- verify_deprecated_scripts_removed ---"
if [ -f "$(cd "$(dirname "$0")/.." && pwd)/scripts/gemini-deploy.sh" ]; then
    echo "❌ Assertion Failed: scripts/gemini-deploy.sh still exists"
    exit 1
fi
if [ -f "$(cd "$(dirname "$0")/.." && pwd)/tests/test_gemini_deploy.sh" ]; then
    echo "❌ Assertion Failed: tests/test_gemini_deploy.sh still exists"
    exit 1
fi
echo "✅ Passed: Deprecated scripts removed."

echo "--- verify_release_ignore_cleaned ---"
if grep -q "gemini-deploy.sh" "$(cd "$(dirname "$0")/.." && pwd)"/.release_ignore; then
    echo "❌ Assertion Failed: .release_ignore still contains gemini-deploy.sh"
    exit 1
fi
echo "✅ Passed: .release_ignore is clean."

echo "All PR-003 assertions passed!"
