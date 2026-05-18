#!/bin/bash
set -eo pipefail

DIST_DIR=".dist"

echo "Building release to $DIST_DIR..."

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

if [ ! -f .release_ignore ]; then
  echo "Warning: .release_ignore not found in $(pwd). Creating default."
  python3 - <<'PY'
from pathlib import Path
Path('.release_ignore').write_text('''\
.git/
.sdlc/
.sdlc_runs/
docs/
tests/
*.log
*.diff
.review_count
memory/
.venv/
fake-bin/
''', encoding='utf-8')
PY
fi

rsync -av --exclude-from='.gitignore' --exclude-from='.release_ignore' --exclude="$DIST_DIR/" ./ "$DIST_DIR/"

echo "Build complete."
