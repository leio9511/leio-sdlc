#!/bin/bash
set -e

echo "--- verify_deprecated_scripts_removed ---"
if [ -f "/root/.openclaw/workspace/projects/leio-sdlc/scripts/gemini-deploy.sh" ]; then
    echo "❌ Assertion Failed: scripts/gemini-deploy.sh still exists"
    exit 1
fi
if [ -f "/root/.openclaw/workspace/projects/leio-sdlc/tests/test_gemini_deploy.sh" ]; then
    echo "❌ Assertion Failed: tests/test_gemini_deploy.sh still exists"
    exit 1
fi
echo "✅ Passed: Deprecated scripts removed."

echo "--- verify_release_ignore_cleaned ---"
if grep -q "gemini-deploy.sh" /root/.openclaw/workspace/projects/leio-sdlc/.release_ignore; then
    echo "❌ Assertion Failed: .release_ignore still contains gemini-deploy.sh"
    exit 1
fi
echo "✅ Passed: .release_ignore is clean."

echo "All PR-003 assertions passed!"
