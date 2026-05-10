#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

resolve_home_root() {
    if [ -n "${HOME_MOCK:-}" ]; then
        printf '%s\n' "$HOME_MOCK"
    else
        printf '%s\n' "$HOME"
    fi
}

resolve_skills_dir() {
    local openclaw_home="$1"
    if [ -n "${HOME_MOCK:-}" ]; then
        printf '%s\n' "$openclaw_home/skills"
    else
        printf '%s\n' "${SDLC_RUNTIME_DIR:-$openclaw_home/skills}"
    fi
}

perform_hard_copy_rollback() {
    local SLUG="leio-sdlc"
    local HOME_ROOT
    HOME_ROOT="$(resolve_home_root)"
    local OPENCLAW_HOME="$HOME_ROOT/.openclaw"
    local RELEASES_ROOT="$OPENCLAW_HOME/.releases"
    local SKILLS_DIR
    SKILLS_DIR="$(resolve_skills_dir "$OPENCLAW_HOME")"
    local PROD_DIR="$SKILLS_DIR/$SLUG"
    local RELEASES_DIR="$RELEASES_ROOT/$SLUG"

    local NO_RESTART=false
    for arg in "$@"; do
        case "$arg" in
            --no-restart)
                NO_RESTART=true
                ;;
        esac
    done

    echo "[$(date '+%H:%M:%S')] Starting hard-copy rollback flow for $SLUG"
    echo "📁 Restoring canonical production directory: $PROD_DIR"
    echo "📦 Reading canonical backups from: $RELEASES_DIR"

    if [ ! -d "$RELEASES_DIR" ]; then
        echo "❌ No releases directory found at $RELEASES_DIR"
        exit 1
    fi

    local LATEST_BACKUP
    LATEST_BACKUP=$(ls -t "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | head -n 1)
    if [ -z "$LATEST_BACKUP" ]; then
        echo "❌ No backup tarballs found in $RELEASES_DIR"
        exit 1
    fi

    echo "📦 Found latest backup: $LATEST_BACKUP"

    if [ -f "$PROD_DIR/.sdlc_repo.lock" ] || [ -f "$PROD_DIR/.coder_session" ] || [ -f "$PROD_DIR/.sdlc_lock_manifest.json" ]; then
        echo "❌ [FATAL_LOCK] Cannot rollback while another SDLC pipeline is active (.sdlc_repo.lock, .coder_session, or .sdlc_lock_manifest.json found)."
        exit 1
    fi

    mkdir -p "$SKILLS_DIR"

    local OLD_DIR="$SKILLS_DIR/.old_$SLUG"
    rm -rf "$OLD_DIR"
    if [ -L "$PROD_DIR" ]; then
        echo "🗑️ Removing symlinked production directory before restore..."
        rm -f "$PROD_DIR"
    elif [ -e "$PROD_DIR" ]; then
        echo "🗑️ Moving broken directory out of the way..."
        mv "$PROD_DIR" "$OLD_DIR"
    fi

    echo "♻️ Restoring backup to $PROD_DIR..."
    tar -xzf "$LATEST_BACKUP" -C "$SKILLS_DIR"
    rm -rf "$OLD_DIR"

    if [ "$NO_RESTART" != "true" ]; then
        if command -v openclaw >/dev/null 2>&1; then
            if [ -z "${HOME_MOCK:-}" ]; then
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
