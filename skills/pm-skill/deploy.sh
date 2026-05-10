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
PROD_DIR="$SKILLS_DIR/$SLUG"
RELEASES_DIR="$RELEASES_ROOT/$SLUG"

NO_RESTART=false
for arg in "$@"; do
    case $arg in
        --no-restart)
        NO_RESTART=true
        shift
        ;;
    esac
done

echo "Deploying $SLUG..."

if [ -f "scripts/build_release.sh" ]; then
    bash "scripts/build_release.sh"
fi

mkdir -p "$SKILLS_DIR"
RELEASE_ID=$(date +"%Y%m%d_%H%M%S")

if [ -e "$PROD_DIR" ]; then
    mkdir -p "$RELEASES_DIR"
    if [ -L "$PROD_DIR" ]; then
        rm -f "$PROD_DIR"
    else
        tar -czf "$RELEASES_DIR/backup_${RELEASE_ID}.tar.gz" -C "$SKILLS_DIR" "$SLUG"
    fi
fi

TMP_DIR="$SKILLS_DIR/.tmp_$SLUG"
OLD_DIR="$SKILLS_DIR/.old_$SLUG"
rm -rf "$TMP_DIR" "$OLD_DIR"
mkdir -p "$TMP_DIR"

if [ -d "dist" ] && [ "$(ls -A dist 2>/dev/null)" ]; then
    cp -a dist/. "$TMP_DIR/"
else
    rsync -a --exclude=.git --exclude=__pycache__ ./ "$TMP_DIR/"
fi

# Package shared dependencies from monorepo root
mkdir -p "$TMP_DIR/scripts"
cp ../../scripts/agent_driver.py "$TMP_DIR/scripts/"
cp ../../scripts/utils_notification.py "$TMP_DIR/scripts/"

if [ -e "$PROD_DIR" ]; then
    mv "$PROD_DIR" "$OLD_DIR"
fi
mv -T "$TMP_DIR" "$PROD_DIR"
rm -rf "$OLD_DIR"

ls -dt "$RELEASES_DIR"/backup_*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm -f

echo "✅ $SLUG deployed."

if command -v gemini >/dev/null 2>&1; then
    echo "🔗 Gemini CLI detected. Linking skill for dual compatibility..."
    gemini skills link "$PROD_DIR" --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
fi
