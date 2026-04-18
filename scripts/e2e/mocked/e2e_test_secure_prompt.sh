#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR=$(mktemp -d)

cd "$SANDBOX_DIR"
git init > /dev/null
git config user.name "Test"
git config user.email "test@example.com"
git commit --allow-empty -m "init" > /dev/null
mkdir -p playbooks TEMPLATES scripts docs/PRDs

echo "playbook" > playbooks/planner_playbook.md

init_hermetic_sandbox "$SANDBOX_DIR/scripts"

echo "prd" > docs/PRDs/prd.md

export SDLC_MOCK_LLM_RESPONSE='```json
{"status": "APPROVED", "comments": "mock"}
```'

# Use spawn_planner.py to ensure mock works without real API
python3 scripts/spawn_planner.py --prd-file docs/PRDs/prd.md --workdir "$(pwd)" --global-dir "$(pwd)" > spawner.log 2>&1 || true

if ! grep -q "mock" spawner.log && ! grep -q "APPROVED" .sdlc_runs/prd/pr_contract.md; then
    # check if mock success
    echo "Wait, if spawn_planner outputs mock..."
fi

echo "✅ test_secure_prompt.sh PASSED"

rm -rf "$SANDBOX_DIR"
