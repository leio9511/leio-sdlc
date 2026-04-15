#!/bin/bash
# test_035_headless_deploy.sh
# Purpose: Verify that deploy.sh executes without interactive prompts and doesn't stall

# Mock the gemini CLI command to verify it's called with --consent
mkdir -p /tmp/mock_bin
cat << 'EOF' > /tmp/mock_bin/gemini
#!/bin/bash
if [[ "$*" == *"skills link"* ]]; then
    if [[ "$*" == *"--consent"* ]]; then
        echo "Mock Gemini CLI: Consent given, proceeding headlessly."
        exit 0
    else
        echo "Mock Gemini CLI: Stalling... awaiting interactive input [Y/n]"
        sleep 5
        exit 1
    fi
fi
exit 0
EOF
chmod +x /tmp/mock_bin/gemini

# Run the deploy script in a controlled environment
export PATH="/tmp/mock_bin:$PATH"
export HOME_MOCK="/tmp/headless_deploy_test_home"
export NO_RESTART=true

# Create a dummy project environment
cd "$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p .dist
touch .dist/dummy_file

# Run the deploy.sh
./deploy.sh --no-restart > /tmp/deploy_output.log 2>&1
EXIT_CODE=$?

# Verify output
if grep -q "Mock Gemini CLI: Consent given" /tmp/deploy_output.log; then
    echo "✅ SUCCESS: Headless deployment confirmed."
else
    echo "❌ FAILURE: Headless deployment stalled or failed to use --consent."
    cat /tmp/deploy_output.log
    rm -rf /tmp/mock_bin /tmp/headless_deploy_test_home /tmp/deploy_output.log
    exit 1
fi

echo "--- Running test_deploy_without_openclaw ---"
unset HOME_MOCK
unset NO_RESTART
export PATH="/tmp/mock_bin:/usr/bin:/bin"

# We want to make sure the openclaw command is absolutely not available
./deploy.sh > /tmp/deploy_no_openclaw.log 2>&1
EXIT_1=$?

./kit-deploy.sh > /tmp/kit_deploy_no_openclaw.log 2>&1
EXIT_2=$?

if [ $EXIT_1 -ne 0 ] || [ $EXIT_2 -ne 0 ]; then
    echo "❌ FAILURE: deploy or kit-deploy failed without openclaw."
    cat /tmp/deploy_no_openclaw.log
    cat /tmp/kit_deploy_no_openclaw.log
    rm -rf /tmp/mock_bin /tmp/headless_deploy_test_home /tmp/deploy_output.log /tmp/deploy_no_openclaw.log /tmp/kit_deploy_no_openclaw.log
    exit 1
fi

if grep -qi "command not found" /tmp/deploy_no_openclaw.log /tmp/kit_deploy_no_openclaw.log; then
    echo "❌ FAILURE: scripts output 'command not found'."
    grep -i "command not found" /tmp/deploy_no_openclaw.log /tmp/kit_deploy_no_openclaw.log
    rm -rf /tmp/mock_bin /tmp/headless_deploy_test_home /tmp/deploy_output.log /tmp/deploy_no_openclaw.log /tmp/kit_deploy_no_openclaw.log
    exit 1
fi

echo "✅ SUCCESS: test_deploy_without_openclaw passed."
rm -rf /tmp/mock_bin /tmp/headless_deploy_test_home /tmp/deploy_output.log /tmp/deploy_no_openclaw.log /tmp/kit_deploy_no_openclaw.log
exit 0
