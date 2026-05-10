#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

SLUG="pm-skill"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

HOME_ROOT="${HOME_MOCK:-$HOME}"
OPENCLAW_HOME="$HOME_ROOT/.openclaw"
RELEASES_ROOT="$OPENCLAW_HOME/.releases"
if [ -n "$HOME_MOCK" ]; then
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

echo "Deploying $SLUG..."
mkdir -p "$SKILLS_DIR"
mkdir -p "$RELEASES_DIR"
RELEASE_ID=$(date +"%Y%m%d_%H%M%S")

if [ -e "$PROD_DIR" ]; then
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

# Stage the skill directory
rsync -a --exclude=.git --exclude=__pycache__ "$REPO_ROOT/skills/$SLUG/" "$TMP_DIR/"

# Package dependencies from monorepo root
mkdir -p "$TMP_DIR/scripts"
cp "$REPO_ROOT/scripts/agent_driver.py" "$TMP_DIR/scripts/"
cp "$REPO_ROOT/scripts/utils_notification.py" "$TMP_DIR/scripts/"

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
