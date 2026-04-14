#!/bin/bash
set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"

SANDBOX_DIR=$(mktemp -d)

cd "$SANDBOX_DIR"
git init > /dev/null
git config user.name "Test"
git config user.email "test@example.com"
git commit --allow-empty -m "init" > /dev/null
mkdir -p playbooks TEMPLATES scripts docs/PRDs

echo "playbook" > playbooks/planner_playbook.md

init_hermetic_sandbox "$SANDBOX_DIR/scripts"

# Create a fake openclaw wrapper to inspect arguments
cat << 'INNER_EOF' > scripts/openclaw
#!/bin/bash
# We write to a file in the parent directory to ensure it survives
LOG_FILE="$(cd "$(dirname "$0")/.." && pwd)/openclaw.log"
echo "OPENCLAW_CALLED_WITH: $*" >> "$LOG_FILE"

# Look for /tmp/sdlc_prompt_ or .tmp/sdlc_prompt_ in ANY argument
for arg in "$@"; do
    if [[ "$arg" == *".tmp/sdlc_prompt_"* ]] || [[ "$arg" == *"/tmp/sdlc_prompt_"* ]]; then
        # Capture the full path
        FILE=$(echo "$arg" | grep -oP '(?<=instructions from )[^ ]*(?=\.txt)')
        if [ -z "$FILE" ]; then
             FILE=$(echo "$arg" | grep -oE '[^ ]*sdlc_prompt_[^ ]+\.txt')
        fi
        
        if [ -n "$FILE" ]; then
            # Ensure extension is there if captured via instructions from
            if [[ "$FILE" != *".txt" ]]; then
                FILE="${FILE}.txt"
            fi
            if [ -f "$FILE" ]; then
                PERMS=$(stat -c "%a" "$FILE")
                echo "FILE:$FILE:PERMS:$PERMS" >> "$LOG_FILE"
            else
                echo "FILE:$FILE:NOT_FOUND" >> "$LOG_FILE"
            fi
        fi
    fi
done
INNER_EOF
chmod +x scripts/openclaw

# Run spawner with PATH override
echo "prd" > docs/PRDs/prd.md
export PATH="$(pwd)/scripts:$PATH"
# Use spawn_planner.py because it actually uses invoke_agent
python3 scripts/spawn_planner.py --prd-file docs/PRDs/prd.md --workdir "$(pwd)" --global-dir "$(pwd)" > spawner.log 2>&1 || true

# Check openclaw.log
if [ ! -f "openclaw.log" ]; then
    echo "❌ test_secure_prompt.sh FAILED: openclaw.log not found."
    cat spawner.log
    exit 1
fi

if ! grep -q "PERMS:600" openclaw.log; then
    echo "❌ test_secure_prompt.sh FAILED: Secure prompt not verified in openclaw.log."
    cat openclaw.log
    exit 1
fi

echo "✅ test_secure_prompt.sh PASSED"

rm -rf "$SANDBOX_DIR"
