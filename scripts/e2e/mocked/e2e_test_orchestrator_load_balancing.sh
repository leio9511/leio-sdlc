#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/../../.." && pwd)"

export PYTHONPATH="$ROOT_DIR/scripts:$PYTHONPATH"

# Setup temp dir
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

CONFIG_DIR="$TMP_DIR/config"
RUNS_DIR="$TMP_DIR/.sdlc_runs"
mkdir -p "$CONFIG_DIR"
mkdir -p "$RUNS_DIR"

CONFIG_FILE="$CONFIG_DIR/sdlc_config.json"
STATE_FILE="$RUNS_DIR/.session_keys.json"

cat << 'JSON' > "$CONFIG_FILE"
{
  "gemini_api_keys": ["KEY_1_00000001", "KEY_2_00000002", "KEY_3_00000003"]
}
JSON

# Python harness
HARNESS="$TMP_DIR/test_harness.py"
cat << 'PYEOF' > "$HARNESS"
import sys
import json
from utils_api_key import assign_gemini_api_key

def main():
    session_key = sys.argv[1]
    config_file = sys.argv[2]
    state_file = sys.argv[3]
    with open(config_file, "r") as f:
        keys = json.load(f).get("gemini_api_keys", [])
    assigned = assign_gemini_api_key(session_key, {"gemini_api_keys": keys}, state_file)
    print(assigned)

if __name__ == "__main__":
    main()
PYEOF

echo "Testing First Assignment & File-Lock Stability..."
pids=""
for i in {1..20}; do
    python3 "$HARNESS" "sess_test" "$CONFIG_FILE" "$STATE_FILE" > "$TMP_DIR/out_$i" &
    pids="$pids $!"
done
wait $pids

# Verify all outputs are the same
ASSIGNED=$(cat "$TMP_DIR/out_1")
for i in {2..20}; do
    out=$(cat "$TMP_DIR/out_$i")
    if [ "$out" != "$ASSIGNED" ]; then
        echo "FAIL: Concurrent invocations returned different keys ($out vs $ASSIGNED)"
        exit 1
    fi
done
echo "Concurrent assignment passed. Assigned: $ASSIGNED"

echo "Testing Anti-Drift Stickiness..."
# Modify config to change order
cat << 'JSON' > "$CONFIG_FILE"
{
  "gemini_api_keys": ["KEY_X_99999999", "KEY_3_00000003", "KEY_2_00000002", "KEY_1_00000001"]
}
JSON
NEW_ASSIGNED=$(python3 "$HARNESS" "sess_test" "$CONFIG_FILE" "$STATE_FILE")
if [ "$NEW_ASSIGNED" != "$ASSIGNED" ]; then
    echo "FAIL: Anti-Drift failed. Returned $NEW_ASSIGNED instead of $ASSIGNED"
    exit 1
fi
echo "Anti-Drift passed."

echo "Testing Graceful Degradation..."
# Delete the assigned key from config
cat << 'JSON' > "$CONFIG_FILE"
{
  "gemini_api_keys": ["KEY_X_99999999", "KEY_Y_88888888"]
}
JSON
DEGRADED_ASSIGNED=$(python3 "$HARNESS" "sess_test" "$CONFIG_FILE" "$STATE_FILE")
if [ "$DEGRADED_ASSIGNED" == "$ASSIGNED" ]; then
    echo "FAIL: Graceful Degradation failed to return a new key"
    exit 1
fi
if [[ "$DEGRADED_ASSIGNED" != "KEY_X_99999999" && "$DEGRADED_ASSIGNED" != "KEY_Y_88888888" ]]; then
    echo "FAIL: Graceful Degradation returned invalid key $DEGRADED_ASSIGNED"
    exit 1
fi
echo "Graceful Degradation passed. Assigned new key: $DEGRADED_ASSIGNED"

echo "Testing Backward Compatibility..."
cat << 'JSON' > "$CONFIG_FILE"
{}
JSON
EMPTY_ASSIGNED=$(python3 "$HARNESS" "sess_test" "$CONFIG_FILE" "$STATE_FILE")
if [ "$EMPTY_ASSIGNED" != "None" ]; then
    echo "FAIL: Empty config didn't return None. Returned: $EMPTY_ASSIGNED"
    exit 1
fi
echo "Backward Compatibility passed."

echo "All e2e mock tests passed."