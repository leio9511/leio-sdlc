#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

echo "Sandbox created at $TEMP_DIR"
cd "$TEMP_DIR"

init_hermetic_sandbox "$TEMP_DIR/scripts"

# Paths
SPAWN_REVIEWER="$TEMP_DIR/scripts/spawn_reviewer.py"
MOCK_GLOBAL="$TEMP_DIR/mock_global_reviewer"
RUN_DIR="$MOCK_GLOBAL/.sdlc_runs/dummy_prd"
mkdir -p "$TEMP_DIR/TEMPLATES"
touch "$TEMP_DIR/TEMPLATES/review_report.json.template"

echo "mock pr" > pr.md
echo "mock diff" > diff.txt

# We need to mock openclaw binary
mkdir -p "$TEMP_DIR/bin"
mkdir -p "$RUN_DIR"
export PATH="$TEMP_DIR/bin:$PATH"

echo "=== T1: Agent writes output to artifact ==="
# Mock openclaw to output something
cat << 'EOF' > "$TEMP_DIR/bin/openclaw"
#!/bin/bash
echo "Agent executed and output something"
exit 0
EOF
chmod +x "$TEMP_DIR/bin/openclaw"
cp "$TEMP_DIR/bin/openclaw" "$TEMP_DIR/bin/gemini"

if ! python3 "$SPAWN_REVIEWER" --pr-file pr.md --diff-target HEAD --workdir . --override-diff-file diff.txt --run-dir "$RUN_DIR" --out-file "$RUN_DIR/review_report.json" --global-dir "$MOCK_GLOBAL" 2>stderr.log; then
    echo "❌ T1 Failed"
    cat stderr.log
    exit 1
fi

if grep -q "Agent executed and output something" "$RUN_DIR/review_report.json"; then
    echo "✅ T1 Passed: Output written to artifact"
else
    echo "❌ T1 Failed: Output not written"
    cat "$RUN_DIR/review_report.json"
    exit 1
fi

echo "=== T2: Agent creates artifact ==="
# Mock openclaw to create the file
cat << EOF > "$TEMP_DIR/bin/openclaw"
#!/bin/bash
echo "Agent executed and wrote file"
touch "$RUN_DIR/review_report.json"
exit 0
EOF
chmod +x "$TEMP_DIR/bin/openclaw"
cp "$TEMP_DIR/bin/openclaw" "$TEMP_DIR/bin/gemini"

if ! python3 "$SPAWN_REVIEWER" --pr-file pr.md --diff-target HEAD --workdir . --override-diff-file diff.txt --run-dir "$RUN_DIR" --out-file "$RUN_DIR/review_report.json" --global-dir "$MOCK_GLOBAL"; then
    echo "❌ T2 Failed: python script should have exited with 0"
    exit 1
fi
echo "✅ T2 Passed: Allowed successful run"
