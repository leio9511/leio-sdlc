#!/bin/bash
cd "$(dirname "$0")" || exit 1
set -e

SLUG="pm-skill"

HOME_ROOT=""
if [ -n "${HOME_MOCK:-}" ]; then
    HOME_ROOT="$HOME_MOCK"
else
    HOME_ROOT="$HOME"
fi

OPENCLAW_HOME="$HOME_ROOT/.openclaw"
RELEASES_ROOT="$OPENCLAW_HOME/.releases"
if [ -n "${HOME_MOCK:-}" ]; then
    SKILLS_DIR="$OPENCLAW_HOME/skills"
else
    SKILLS_DIR="${SDLC_RUNTIME_DIR:-$OPENCLAW_HOME/skills}"
fi
RELEASES_DIR="$RELEASES_ROOT/$SLUG"
PROD_DIR="$SKILLS_DIR/$SLUG"

NO_RESTART=false
for arg in "$@"; do
    case $arg in
        --no-restart)
        NO_RESTART=true
        shift
        ;;
    esac
done

if [ ! -d "$PROD_DIR" ]; then
    echo "❌ No production directory found at $PROD_DIR"
    exit 1
fi

if [ ! -d "$RELEASES_DIR" ]; then
    echo "❌ No releases directory found at $RELEASES_DIR"
    exit 1
fi

LATEST_BACKUP=$(ls -t "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | head -n 1)
if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ No backup tarballs found in $RELEASES_DIR"
    exit 1
fi

# Orchestrator standard guardrails: Prevent rollback during active SDLC sessions
if [ -f "$PROD_DIR/.sdlc_repo.lock" ] || [ -f "$PROD_DIR/.coder_session" ] || [ -f "$PROD_DIR/.sdlc_lock_manifest.json" ]; then
    echo "❌ [FATAL_LOCK] Cannot rollback while another SDLC pipeline is active (.sdlc_repo.lock, .coder_session, or .sdlc_lock_manifest.json found)."
    exit 1
fi

echo "Rolling back $SLUG from $LATEST_BACKUP..."
OLD_DIR="$SKILLS_DIR/.old_$SLUG"
rm -rf "$OLD_DIR"
mv "$PROD_DIR" "$OLD_DIR"
tar -xzf "$LATEST_BACKUP" -C "$SKILLS_DIR"
rm -rf "$OLD_DIR"

if [ "$NO_RESTART" != "true" ]; then
    if command -v openclaw >/dev/null 2>&1; then
        if [ -z "$HOME_MOCK" ]; then
            echo "🔄 Restarting OpenClaw gateway..."
            openclaw gateway restart || echo "⚠️ Gateway restart failed or not available."
        else
            echo "🔄 Skipping OpenClaw gateway restart (mock environment detected)..."
        fi
    fi
else
    echo "🔄 Skipping OpenClaw gateway restart (--no-restart passed)..."
fi
echo "✅ Rollback complete for $SLUG."
