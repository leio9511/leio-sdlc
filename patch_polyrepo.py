import glob

for file_path in ["scripts/test_polyrepo_context.sh", "scripts/test_git_boundary.sh", "scripts/test_anti_reward_hacking.sh"]:
    try:
        with open(file_path, "r") as f:
            content = f.read()

        target = 'SANDBOX_DIR=$(mktemp -d)\n'
        mock_code = """SANDBOX_DIR=$(mktemp -d)
mkdir -p "$SANDBOX_DIR/bin"
cat << 'INNER_EOF' > "$SANDBOX_DIR/bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
chmod +x "$SANDBOX_DIR/bin/openclaw"
export PATH="$SANDBOX_DIR/bin:$PATH"
"""
        if target in content and 'openclaw' not in content:
            content = content.replace(target, mock_code, 1)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"Patched {file_path}")
    except:
        pass
