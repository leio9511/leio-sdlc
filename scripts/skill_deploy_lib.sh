#!/bin/bash
# skill_deploy_lib.sh - Generic skill deploy/rollback substrate for repository skills
# Provides skill_deploy_run and skill_rollback_run consumed by skill_deploy.sh / skill_rollback.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# skill_deploy_run <slug> [--no-restart]
# ---------------------------------------------------------------------------
skill_deploy_run() {
    local slug="${1:-}"
    shift || true

    # -- Parse optional flags --
    local NO_RESTART=false
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-restart) NO_RESTART=true ; shift ;;
            *) shift ;;
        esac
    done

    # -- 3.1.1 Slug validation (fail-fast) --
    if [ -z "$slug" ]; then
        echo "Error: slug must not be empty" >&2
        return 1
    fi
    if [[ "$slug" == *"/"* ]]; then
        echo "Error: slug must not contain '/'" >&2
        return 1
    fi
    if [[ "$slug" == *".."* ]]; then
        echo "Error: slug must not contain '..'" >&2
        return 1
    fi

    # -- 3.1.2 Source validation --
    local SCRIPT_DIR
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local REPO_ROOT
    REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

    local SOURCE_DIR="$REPO_ROOT/skills/$slug"

    if [ ! -d "$SOURCE_DIR" ]; then
        echo "Error: skill source directory not found: $SOURCE_DIR" >&2
        return 1
    fi
    if [ ! -f "$SOURCE_DIR/SKILL.md" ]; then
        echo "Error: SKILL.md not found in skill source: $SOURCE_DIR" >&2
        return 1
    fi

    # -- 3.1.3 Path resolution --
    local HOME_ROOT="${HOME_MOCK:-$HOME}"
    local OPENCLAW_HOME="$HOME_ROOT/.openclaw"
    local SKILLS_DIR
    if [ -n "${HOME_MOCK:-}" ]; then
        SKILLS_DIR="$OPENCLAW_HOME/skills"
    else
        SKILLS_DIR="${SDLC_RUNTIME_DIR:-$OPENCLAW_HOME/skills}"
    fi
    local RELEASES_DIR="$OPENCLAW_HOME/.releases/$slug"
    local PROD_DIR="$SKILLS_DIR/$slug"
    local TMP_DIR="$SKILLS_DIR/.tmp_$slug"
    local OLD_DIR="$SKILLS_DIR/.old_$slug"

    # Ensure base directories exist
    mkdir -p "$SKILLS_DIR"
    mkdir -p "$RELEASES_DIR"

    # Remove any stale staging artifacts from prior runs
    rm -rf "$TMP_DIR" "$OLD_DIR"

    # -- 3.1.4 + 3.1.5 Source staging with exclusions --
    mkdir -p "$TMP_DIR"

    local -a EXCLUDE_ARGS=()
    # Common default excludes
    EXCLUDE_ARGS+=(--exclude='.git')
    EXCLUDE_ARGS+=(--exclude='__pycache__')
    EXCLUDE_ARGS+=(--exclude='dist')
    EXCLUDE_ARGS+=(--exclude='.pytest_cache')
    EXCLUDE_ARGS+=(--exclude='.mypy_cache')
    EXCLUDE_ARGS+=(--exclude='.ruff_cache')

    # Optional skill-local .release_ignore (extends, does not re-include)
    if [ -f "$SOURCE_DIR/.release_ignore" ]; then
        EXCLUDE_ARGS+=(--exclude-from="$SOURCE_DIR/.release_ignore")
    fi

    rsync -a "${EXCLUDE_ARGS[@]}" "$SOURCE_DIR/" "$TMP_DIR/"

    # -- 3.1.6 Backup of existing runtime --
    if [ -e "$PROD_DIR" ]; then
        if [ -L "$PROD_DIR" ]; then
            # Do not back up a symlink; just remove it
            rm -f "$PROD_DIR"
        else
            local RELEASE_ID
            RELEASE_ID=$(date +"%Y%m%d_%H%M%S")
            tar -czf "$RELEASES_DIR/backup_${RELEASE_ID}.tar.gz" -C "$SKILLS_DIR" "$slug"
        fi
    fi

    # -- 3.1.7 Atomic promotion --
    if [ -e "$PROD_DIR" ]; then
        mv "$PROD_DIR" "$OLD_DIR"
    fi
    mv -T "$TMP_DIR" "$PROD_DIR"
    rm -rf "$OLD_DIR"

    # -- Backup retention: keep at most 3 latest backups --
    local _found_backups
    _found_backups=$(ls -dt "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null || true)
    if [ -n "$_found_backups" ]; then
        echo "$_found_backups" | tail -n +4 | xargs -r rm -f
    fi

    # -- 3.1.8 Gemini best-effort linking --
    if command -v gemini >/dev/null 2>&1; then
        HOME="$HOME_ROOT" gemini skills link "$PROD_DIR" --consent || echo "Warning: Gemini link failed, but deployment succeeded." >&2
    fi

    # -- 3.1.9 Cleanup --
    rm -rf "$TMP_DIR" "$OLD_DIR"

    # --no-restart is accepted as a compatibility no-op for deploy.
    # Gateway restart is not part of the skill deploy contract (it belongs to root deploy).
}

# ---------------------------------------------------------------------------
# skill_rollback_run <slug> [--no-restart]
# ---------------------------------------------------------------------------
skill_rollback_run() {
    local slug="${1:-}"
    shift || true

    # -- Parse optional flags --
    local NO_RESTART=false
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-restart) NO_RESTART=true ; shift ;;
            *) shift ;;
        esac
    done

    # -- Slug validation --
    if [ -z "$slug" ]; then
        echo "Error: slug must not be empty" >&2
        return 1
    fi
    if [[ "$slug" == *"/"* ]]; then
        echo "Error: slug must not contain '/'" >&2
        return 1
    fi
    if [[ "$slug" == *".."* ]]; then
        echo "Error: slug must not contain '..'" >&2
        return 1
    fi

    # -- Path resolution --
    local HOME_ROOT="${HOME_MOCK:-$HOME}"
    local OPENCLAW_HOME="$HOME_ROOT/.openclaw"
    local SKILLS_DIR
    if [ -n "${HOME_MOCK:-}" ]; then
        SKILLS_DIR="$OPENCLAW_HOME/skills"
    else
        SKILLS_DIR="${SDLC_RUNTIME_DIR:-$OPENCLAW_HOME/skills}"
    fi
    local RELEASES_DIR="$OPENCLAW_HOME/.releases/$slug"
    local PROD_DIR="$SKILLS_DIR/$slug"

    # -- Locate latest backup --
    local LATEST_BACKUP
    LATEST_BACKUP=$(ls -t "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | head -1 || true)

    if [ -z "$LATEST_BACKUP" ]; then
        echo "Error: no backup found for '$slug' in $RELEASES_DIR" >&2
        return 1
    fi

    # -- Remove current runtime --
    if [ -e "$PROD_DIR" ] || [ -L "$PROD_DIR" ]; then
        rm -rf "$PROD_DIR"
    fi

    # -- Restore from backup --
    mkdir -p "$SKILLS_DIR"
    tar -xzf "$LATEST_BACKUP" -C "$SKILLS_DIR"

    # -- Gateway restart (rollback): --no-restart suppresses, HOME_MOCK skips --
    if [ "$NO_RESTART" != "true" ] && [ -z "${HOME_MOCK:-}" ]; then
        if command -v openclaw >/dev/null 2>&1; then
            openclaw gateway restart || echo "Warning: Gateway restart failed." >&2
        fi
    fi
}
