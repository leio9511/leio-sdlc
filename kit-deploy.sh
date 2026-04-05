#!/bin/bash
set -e
echo "Starting Kit Deployment..."
bash deploy.sh --no-restart
bash skills/pm-skill/deploy.sh --no-restart
bash skills/leio-auditor/deploy.sh --no-restart

if [ -z "$HOME_MOCK" ]; then
    echo "🔄 Restarting OpenClaw gateway for Kit..."
    openclaw gateway restart || echo "⚠️ Gateway restart failed or not available."
fi
echo "✅ Kit deployment complete."
