#!/bin/bash
# Test Case 1: verify_audit_report_completeness
# Check that docs/OpenClaw_CLI_Compatibility_Audit.md contains a reference to scripts/rollback.sh

AUDIT_FILE="/root/projects/leio-sdlc/docs/OpenClaw_CLI_Compatibility_Audit.md"
ROLLBACK_SCRIPT="scripts/rollback.sh"

echo "Running Test Case 1: verify_audit_report_completeness..."
if grep -q "$ROLLBACK_SCRIPT" "$AUDIT_FILE"; then
    echo "✅ Test Case 1 PASSED: $ROLLBACK_SCRIPT found in $AUDIT_FILE"
else
    echo "❌ Test Case 1 FAILED: $ROLLBACK_SCRIPT NOT found in $AUDIT_FILE"
    exit 1
fi

# Test Case 2: verify_rollback_script_call_site
# Verify that scripts/rollback.sh indeed contains the openclaw gateway restart command

echo "Running Test Case 2: verify_rollback_script_call_site..."
if grep -q "openclaw gateway restart" "/root/projects/leio-sdlc/$ROLLBACK_SCRIPT"; then
    echo "✅ Test Case 2 PASSED: 'openclaw gateway restart' found in $ROLLBACK_SCRIPT"
else
    echo "❌ Test Case 2 FAILED: 'openclaw gateway restart' NOT found in $ROLLBACK_SCRIPT"
    exit 1
fi

echo "All PR-005 tests passed!"
