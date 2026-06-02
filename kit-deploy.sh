#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# ALLOW_PUBLIC_FALLBACK_LOCAL_OVERRIDE:
# This local override flag allows local developer workstations to automatically
# fall back to the public PyPI registry if the secure/internal corporate registry is incomplete or unreachable.
# This avoids the need for developers to manually create and manage config/engines.local.json.
# In production or secure CI/CD environments, this override should NOT be set, forcing the deployment to
# fail closed for strict compliance.
# You can explicitly disable this override for testing compliance by setting:
# export ALLOW_PUBLIC_FALLBACK_LOCAL_OVERRIDE=false
export ALLOW_PUBLIC_FALLBACK_LOCAL_OVERRIDE="${ALLOW_PUBLIC_FALLBACK_LOCAL_OVERRIDE:-true}"
echo "Starting Kit Deployment..."

root_args=("$@")
child_args=()
preflight_only=false

if [ ${#root_args[@]} -eq 0 ]; then
    root_args=(--no-restart)
    child_args=(--no-restart)
else
    for arg in "${root_args[@]}"; do
        case "$arg" in
            --no-restart)
                child_args+=(--no-restart)
                ;;
            --preflight)
                preflight_only=true
                ;;
        esac
    done
fi

bash "$SCRIPT_DIR/deploy.sh" "${root_args[@]}"

if [ "$preflight_only" = true ]; then
    echo "✅ Kit deployment preflight complete."
    exit 0
fi

for skill_deploy_script in "$SCRIPT_DIR"/skills/*/deploy.sh; do
    if [ -f "$skill_deploy_script" ]; then
        bash "$skill_deploy_script" "${child_args[@]}"
    fi
done

echo "✅ Kit deployment complete."
