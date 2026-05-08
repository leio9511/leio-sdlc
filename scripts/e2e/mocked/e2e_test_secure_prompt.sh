#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR=$(mktemp -d)
init_git_test_sandbox "$SANDBOX_DIR" --baseline-commit

cd "$SANDBOX_DIR"
mkdir -p playbooks TEMPLATES scripts docs/PRDs

echo "playbook" > playbooks/planner_playbook.md

init_hermetic_sandbox "$SANDBOX_DIR/scripts"

echo "prd" > docs/PRDs/prd.md

export SDLC_MOCK_LLM_RESPONSE="MOCKED_RESPONSE"
export SDLC_MOCK_INSPECT_FILE_PERMS="1"

# Use spawn_planner.py to ensure mock works without real API
python3 scripts/spawn_planner.py --enable-exec-from-workspace --prd-file docs/PRDs/prd.md --workdir "$(pwd)" --global-dir "$(pwd)" > spawner.log 2>&1 || true

if ! grep -q "PERMS:600" spawner.log && ! grep -q "PERMS:600" .sdlc_runs/prd/pr_contract.md; then
    echo "❌ test_secure_prompt.sh FAILED: Secure prompt permissions not verified."
    cat spawner.log
    exit 1
fi

echo "✅ test_secure_prompt.sh PASSED"

rm -rf "$SANDBOX_DIR"
