#!/bin/bash
set -e

echo "Setting up Coder Triad Test..."
mkdir -p tests
cat << 'EOF' > tests/dummy_triad_prd_coder.md
# Dummy PRD for Coder
Just a dummy PRD context.
EOF

cat << 'EOF' > tests/dummy_triad_pr_coder.md
# Dummy PR for Coder
CRITICAL: You MUST use the `call:default_api:write` tool to create a file at /root/.openclaw/workspace/projects/leio-sdlc/tests/dummy_generated_output.py containing exactly: print('CODER_TRIAD_SUCCESS')
Do NOT just say you did it. You MUST output the JSON tool call.
EOF

unset SDLC_TEST_MODE
rm -f tests/dummy_generated_output.py

echo "Running Coder..."
python3 scripts/spawn_coder.py --pr-file tests/dummy_triad_pr_coder.md --prd-file tests/dummy_triad_prd_coder.md  --workdir "$(pwd)" > tests/triad_coder.log 2>&1 || true

echo "Asserting Output..."
if [ -f tests/dummy_generated_output.py ] && grep -q "CODER_TRIAD_SUCCESS" tests/dummy_generated_output.py; then
    echo "Coder Triad Test Passed."
    exit 0
else
    echo "Coder Triad Test Failed."
    cat tests/triad_coder.log
    exit 1
fi
