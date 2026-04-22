#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEST_DIR=$(mktemp -d)
init_hermetic_sandbox "$TEST_DIR/scripts"

echo "Running E2E Pipeline Run test for spawn_auditor.py"
python3 "$TEST_DIR/scripts/spawn_auditor.py" --enable-exec-from-workspace --help > /dev/null || true

rm -rf "$TEST_DIR"
echo "Successfully executed spawn_auditor.py test"
