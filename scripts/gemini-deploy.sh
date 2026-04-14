#!/bin/bash
# gemini-deploy.sh - Standalone deployment for leio-sdlc and pm-skill
set -e

TARGET_DIR="${1:-$HOME/sdlc-kit}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Deploying leio-sdlc to $TARGET_DIR..."

# 1. Create target directories
mkdir -p "$TARGET_DIR"

# 2. Copy leio-sdlc (excluding large/unnecessary dirs)
echo "📦 Copying leio-sdlc..."
mkdir -p "$TARGET_DIR/leio-sdlc"
cp -r "$REPO_ROOT"/. "$TARGET_DIR/leio-sdlc/"
# Clean up some bloat in the target if it exists
rm -rf "$TARGET_DIR/leio-sdlc/.git"
rm -rf "$TARGET_DIR/leio-sdlc/.sdlc_runs"

# 3. pm-skill is already inside skills/pm-skill in this repo structure, 
# but we ensure it's accessible or linked if Gemini CLI expects a flat structure.
# The PRD says "install leio-sdlc and pm-skill".
# We'll make sure skills are in a predictable place.
echo "🧩 Ensuring skills are placed correctly..."
mkdir -p "$TARGET_DIR/skills"
if [ -d "$REPO_ROOT/skills/pm-skill" ]; then
    cp -r "$REPO_ROOT/skills/pm-skill" "$TARGET_DIR/skills/"
fi

# 4. Create .sdlc_env template
ENV_FILE="$TARGET_DIR/.sdlc_env"
if [ ! -f "$ENV_FILE" ]; then
    echo "📝 Creating .sdlc_env template..."
    cat > "$ENV_FILE" <<EOF
# SDLC Configuration
export GEMINI_API_KEY="your_api_key_here"
export SDLC_MODEL="google/gemini-3-flash-preview"
export LLM_DRIVER="gemini"
EOF
    echo "✅ Created $ENV_FILE. Please update it with your API key."
else
    echo "ℹ️ $ENV_FILE already exists, skipping."
fi

# 5. Instructions
echo ""
echo "✨ Deployment complete!"
echo "To use:"
echo "  1. Edit $ENV_FILE with your GEMINI_API_KEY."
echo "  2. Source it: 'source $ENV_FILE'"
echo "  3. Run: 'python3 $TARGET_DIR/leio-sdlc/scripts/orchestrator.py --prd path/to/PRD.md'"
