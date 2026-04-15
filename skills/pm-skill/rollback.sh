#!/bin/bash
set -e
SLUG="pm-skill"
HOME_DIR="${HOME_MOCK:-$HOME}"
OPENCLAW_DIR="${SDLC_SKILLS_ROOT:-${HOME_MOCK:-$HOME}/.openclaw/skills}"
RELEASES_DIR="$HOME_DIR/.openclaw/.releases/$SLUG"
PROD_DIR="$OPENCLAW_DIR/$SLUG"

NO_RESTART=false
for arg in "$@"; do
    case $arg in
        --no-restart)
        NO_RESTART=true
        shift
        ;;
    esac
done

LATEST_BACKUP=$(ls -t "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | head -n 1)
if [ -z "$LATEST_BACKUP" ]; then
    echo "No backup found for $SLUG."
    exit 1
fi

echo "Rolling back $SLUG from $LATEST_BACKUP..."
rm -rf "$PROD_DIR"
tar -xzf "$LATEST_BACKUP" -C "$OPENCLAW_DIR"

if [ "$NO_RESTART" != "true" ]; then
    if command -v openclaw >/dev/null 2>&1; then
        echo "🔄 Restarting OpenClaw gateway..."
        openclaw gateway restart || echo "⚠️ Gateway restart failed or not available."
    fi
fi
echo "✅ Rollback complete for $SLUG."
