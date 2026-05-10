#!/bin/bash
set -eo pipefail

DIST_DIR=".dist"
readonly CONTRACT_EXCLUDES=(
  "tests"
  ".sdlc"
  ".sdlc_runs"
)

assert_contract_excludes() {
  local path
  for path in "${CONTRACT_EXCLUDES[@]}"; do
    if [ -e "$DIST_DIR/$path" ]; then
      echo "❌ Release contract violation: $DIST_DIR/$path must be excluded"
      exit 1
    fi
  done
}

echo "Building release to $DIST_DIR..."

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

if [ ! -f .release_ignore ]; then
  echo "Warning: .release_ignore not found in $(pwd). Creating default."
  cat <<EOF > .release_ignore
tests/
.sdlc/
.sdlc_runs/
docs/
memory/
preflight.sh
ARCHITECTURE.md
README.md
package.json
.gitignore
.release_ignore
*.log
*.diff
.review_count
.tmp/
kit-deploy.sh
deploy.sh
EOF
fi

rsync -av --exclude-from='.gitignore' --exclude-from='.release_ignore' --exclude="$DIST_DIR/" ./ "$DIST_DIR/"
assert_contract_excludes

echo "Build complete."
