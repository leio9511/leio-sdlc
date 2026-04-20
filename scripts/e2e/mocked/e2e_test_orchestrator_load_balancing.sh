#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$DIR/../../.." && pwd)"

export PYTHONPATH="$ROOT_DIR/scripts:$PYTHONPATH"

# Setup temp dir
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

# The acceptance criteria wants us to verify file-lock stability for .sdlc_runs/.session_keys.json
STATE_FILE="$TMP_DIR/.sdlc_runs/.session_keys.json"
mkdir -p "$(dirname "$STATE_FILE")"

cat << 'PYEOF' > "$TMP_DIR/test_harness.py"
import sys
import json
from orchestrator import assign_gemini_api_key

def main():
    session_key = sys.argv[1]
    keys = json.loads(sys.argv[2])
    state_file = sys.argv[3]
    
    assigned = assign_gemini_api_key(session_key, keys, state_file)
    print(assigned)

if __name__ == "__main__":
    main()
PYEOF

echo "Scenario 1: Backward Compatibility (No Keys Configured)"
EMPTY_ASSIGNED=$(python3 "$TMP_DIR/test_harness.py" "session_xyz" '[]' "$STATE_FILE")
if [ "$EMPTY_ASSIGNED" != "None" ]; then
    echo "FAIL: Empty config didn't return None. Returned: $EMPTY_ASSIGNED"
    exit 1
fi
echo "Backward Compatibility passed."

echo "Scenario 2: First Execution (Stateful Persistence via Orchestrator)"
for i in {1..20}; do
  python3 "$TMP_DIR/test_harness.py" "session_xyz" '["key_0_A_11111111", "key_1_B_22222222", "key_2_C_33333333"]' "$STATE_FILE" > /dev/null &
done
wait

cat "$STATE_FILE"
echo ""
FINGERPRINT=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('session_xyz', ''))")
if [ -z "$FINGERPRINT" ]; then
    echo "First Execution failed to persist"
    exit 1
fi
echo "Persisted fingerprint: $FINGERPRINT"

echo "Scenario 3: Anti-Drift Stickiness"
RESULT=$(python3 "$TMP_DIR/test_harness.py" "session_xyz" '["key_2_C_33333333", "key_0_A_11111111", "key_1_B_22222222"]' "$STATE_FILE")
echo "Returned key: $RESULT"

if [[ "$RESULT" != *"$FINGERPRINT" ]]; then
    echo "Anti-Drift Stickiness failed! Expected key ending with $FINGERPRINT, got $RESULT"
    exit 1
fi

echo "Scenario 4: Graceful Degradation"
NEW_KEYS=$(python3 -c "import json; print(json.dumps([k for k in ['key_0_A_11111111', 'key_1_B_22222222', 'key_2_C_33333333'] if not k.endswith('$FINGERPRINT')]))")
echo "New keys: $NEW_KEYS"

RESULT_DEG=$(python3 "$TMP_DIR/test_harness.py" "session_xyz" "$NEW_KEYS" "$STATE_FILE")
echo "Returned key after degradation: $RESULT_DEG"

NEW_FINGERPRINT=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('session_xyz', ''))")
if [ -z "$NEW_FINGERPRINT" ]; then
    echo "Graceful degradation failed to update state file"
    exit 1
fi

if [[ "$RESULT_DEG" != *"$NEW_FINGERPRINT" ]]; then
    echo "Graceful Degradation failed! Expected key ending with $NEW_FINGERPRINT, got $RESULT_DEG"
    exit 1
fi
if [ "$NEW_FINGERPRINT" == "$FINGERPRINT" ]; then
    echo "Graceful Degradation failed! Fingerprint didn't change"
    exit 1
fi

echo "All tests passed."
