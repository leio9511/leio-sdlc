#!/usr/bin/env bash
set -e

FAILURES=0

echo "Checking playbooks/reviewer_playbook.md..."
if grep -iqE "git|openclaw" playbooks/reviewer_playbook.md; then
    echo "FAIL: Found 'git' or 'OpenClaw' in playbooks/reviewer_playbook.md"
    grep -inE "git|openclaw" playbooks/reviewer_playbook.md
    FAILURES=$((FAILURES + 1))
else
    echo "PASS: playbooks/reviewer_playbook.md is clean."
fi

echo "Checking config/prompts.json for reviewer prompts..."
if command -v python3 &>/dev/null; then
    python3 -c "
import json, sys
try:
    with open('config/prompts.json', 'r') as f:
        d = json.load(f)
    rev = d.get('reviewer', '')
    sys.stdout.write(rev)
except Exception as e:
    sys.stderr.write(str(e))
    sys.exit(1)
" > .tmp_reviewer_prompt.txt
    
    if grep -iqE "git|openclaw" .tmp_reviewer_prompt.txt; then
        echo "FAIL: Found 'git' or 'OpenClaw' in reviewer prompt in config/prompts.json"
        grep -inE "git|openclaw" .tmp_reviewer_prompt.txt
        FAILURES=$((FAILURES + 1))
    else
        echo "PASS: config/prompts.json reviewer prompt is clean."
    fi
    rm -f .tmp_reviewer_prompt.txt
else
    echo "python3 not found, skipping json parsing"
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "Tests failed."
    exit 1
fi

echo "All tests passed successfully."
exit 0
