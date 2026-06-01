#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./skill_deploy_lib.sh
source "$SCRIPT_DIR/skill_deploy_lib.sh"

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <slug> [--no-restart]" >&2
    exit 1
fi

slug="$1"
shift
skill_rollback_run "$slug" "$@"
