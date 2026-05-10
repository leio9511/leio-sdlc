#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "Starting Kit Deployment..."

deploy_args=("$@")
if [ ${#deploy_args[@]} -eq 0 ]; then
    deploy_args=(--no-restart)
fi

bash "$SCRIPT_DIR/deploy.sh" "${deploy_args[@]}"

for skill_deploy_script in "$SCRIPT_DIR"/skills/*/deploy.sh; do
    if [ -f "$skill_deploy_script" ]; then
        bash "$skill_deploy_script" "${deploy_args[@]}"
    fi
done

echo "✅ Kit deployment complete."
