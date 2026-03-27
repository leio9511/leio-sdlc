import glob

for file_path in glob.glob("scripts/*.sh"):
    with open(file_path, "r") as f:
        content = f.read()

    # Find where orchestrator.py is executed, and inject the mock if it's not already there
    if 'orchestrator.py' in content and 'mock_openclaw' not in content and 'openclaw_calls.log' not in content and file_path != 'scripts/test_missing_channel.sh' and file_path != 'scripts/test_escalation_clean.sh':
        
        target1 = 'TEMP_DIR=$(mktemp -d)'
        target2 = 'TEMP_DIR=$(mktemp -d)\n'
        
        mock_code = """TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/bin"
cat << 'INNER_EOF' > "$TEMP_DIR/bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
chmod +x "$TEMP_DIR/bin/openclaw"
export PATH="$TEMP_DIR/bin:$PATH"
# mock_openclaw added
"""
        if target1 in content and 'mock_openclaw added' not in content:
            content = content.replace(target1, mock_code, 1)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"Patched {file_path}")

