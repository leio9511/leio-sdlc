#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
set -e

# ==========================================
# BOOTSTRAP: ROLLBACK SCRIPT
# ==========================================
# Rollback Hard Copy (Physical Sync)

perform_hard_copy_rollback() {
    local SLUG
    SLUG=$(basename "$PWD")
    local HOME_ROOT
    if [ -n "${HOME_MOCK:-}" ]; then
        HOME_ROOT="$HOME_MOCK"
    else
        HOME_ROOT="$HOME"
    fi

    local OPENCLAW_HOME="$HOME_ROOT/.openclaw"
    local RELEASES_ROOT="$OPENCLAW_HOME/.releases"
    local SKILLS_DIR
    if [ -n "${HOME_MOCK:-}" ]; then
        SKILLS_DIR="$OPENCLAW_HOME/skills"
    else
        SKILLS_DIR="${SDLC_RUNTIME_DIR:-$OPENCLAW_HOME/skills}"
    fi
    local PROD_DIR="$SKILLS_DIR/$SLUG"
    local RELEASES_DIR="$RELEASES_ROOT/$SLUG"
    
    local NO_RESTART=false
    for arg in "$@"; do
        case $arg in
            --no-restart)
            NO_RESTART=true
            shift
            ;;
        esac
    done

    echo "[$(date '+%H:%M:%S')] Starting hard-copy rollback flow for $SLUG"

    if [ ! -d "$PROD_DIR" ]; then
        echo "❌ No production directory found at $PROD_DIR"
        exit 1
    fi

    if [ ! -d "$RELEASES_DIR" ]; then
        echo "❌ No releases directory found at $RELEASES_DIR"
        exit 1
    fi

    local LATEST_BACKUP=$(ls -t "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | head -n 1)

    if [ -z "$LATEST_BACKUP" ]; then
        echo "❌ No backup tarballs found in $RELEASES_DIR"
        exit 1
    fi

    echo "📦 Found latest backup: $LATEST_BACKUP"

    # PR-004 Alignment: Orchestrator standard guardrails
    # Prevent rollback during active SDLC sessions to maintain singleton integrity
    if [ -f "$PROD_DIR/.sdlc_repo.lock" ] || [ -f "$PROD_DIR/.coder_session" ] || [ -f "$PROD_DIR/.sdlc_lock_manifest.json" ]; then
        echo "❌ [FATAL_LOCK] Cannot rollback while another SDLC pipeline is active (.sdlc_repo.lock, .coder_session, or .sdlc_lock_manifest.json found)."
        exit 1
    fi

    # 1. Clear current production directory safely
    local OLD_DIR="$SKILLS_DIR/.old_$SLUG"
    rm -rf "$OLD_DIR"
    echo "🗑️ Moving broken directory out of the way..."
    mv "$PROD_DIR" "$OLD_DIR"

    # 2. Restore backup
    echo "♻️ Restoring backup to $PROD_DIR..."
    tar -xzf "$LATEST_BACKUP" -C "$SKILLS_DIR"
    rm -rf "$OLD_DIR"

    # 3. Gateway Reload
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

    echo "✅ ROLLBACK SUCCESS: $SLUG restored from backup."
}

perform_hard_copy_rollback "$@"
