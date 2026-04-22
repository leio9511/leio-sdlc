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
export RUN_DIR="$MOCK_GLOBAL/.sdlc_runs/dummy_prd"
mkdir -p "$TEMP_DIR/TEMPLATES"
touch "$TEMP_DIR/TEMPLATES/review_report.json.template"

echo "mock pr" > pr.md
echo "mock diff" > diff.txt

mkdir -p "$TEMP_DIR/bin"
mkdir -p "$RUN_DIR"
export PATH="$TEMP_DIR/bin:$PATH"

# Mock openclaw to write to the file
cat << 'MOCK' > "$TEMP_DIR/bin/openclaw"
#!/bin/bash
if [[ "$*" == *"agent"* ]] || [[ "$*" == *"--yolo"* ]]; then
    if [[ "$MOCK_BEHAVIOR" == "no_write" ]]; then
        echo "Did nothing"
    elif [[ "$MOCK_BEHAVIOR" == "invalid_json" ]]; then
        echo "invalid JSON" > "$RUN_DIR/review_report.json"
    elif [[ "$MOCK_BEHAVIOR" == "not_started" ]]; then
        echo '{"overall_assessment": "NOT_STARTED"}' > "$RUN_DIR/review_report.json"
    elif [[ "$MOCK_BEHAVIOR" == "excellent" ]]; then
        echo '{"overall_assessment": "EXCELLENT"}' > "$RUN_DIR/review_report.json"
    fi
    exit 0
fi

MOCK
chmod +x "$TEMP_DIR/bin/openclaw"
cp "$TEMP_DIR/bin/openclaw" "$TEMP_DIR/bin/gemini"

echo "=== T1: Agent does not write file (leaves scaffolding) ==="
export MOCK_BEHAVIOR="no_write"
if python3 "$SPAWN_REVIEWER" --enable-exec-from-workspace --pr-file pr.md --diff-target HEAD --workdir . --override-diff-file diff.txt --run-dir "$RUN_DIR" --out-file "$RUN_DIR/review_report.json" --global-dir "$MOCK_GLOBAL" 2>stderr.log; then
    echo "❌ T1 Failed: Should have failed verification"
    exit 1
fi
echo "✅ T1 Passed"

echo "=== T2: Agent writes invalid JSON ==="
export MOCK_BEHAVIOR="invalid_json"
if python3 "$SPAWN_REVIEWER" --enable-exec-from-workspace --pr-file pr.md --diff-target HEAD --workdir . --override-diff-file diff.txt --run-dir "$RUN_DIR" --out-file "$RUN_DIR/review_report.json" --global-dir "$MOCK_GLOBAL" 2>stderr.log; then
    echo "❌ T2 Failed: Should have failed verification"
    exit 1
fi
echo "✅ T2 Passed"

echo "=== T3: Agent writes EXCELLENT ==="
export MOCK_BEHAVIOR="excellent"
if ! python3 "$SPAWN_REVIEWER" --enable-exec-from-workspace --pr-file pr.md --diff-target HEAD --workdir . --override-diff-file diff.txt --run-dir "$RUN_DIR" --out-file "$RUN_DIR/review_report.json" --global-dir "$MOCK_GLOBAL"; then
    echo "❌ T3 Failed: Should have passed verification"; cat "$RUN_DIR/review_report.json"
    exit 1
fi
echo "✅ T3 Passed"
