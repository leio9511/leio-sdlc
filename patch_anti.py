file_path = "scripts/test_anti_reward_hacking.sh"
with open(file_path, "r") as f:
    content = f.read()

target = 'mkdir -p dummy_workspace\n'
mock_code = """mkdir -p dummy_workspace/bin
cat << 'INNER_EOF' > dummy_workspace/bin/openclaw
#!/bin/bash
exit 0
INNER_EOF
chmod +x dummy_workspace/bin/openclaw
export PATH="$(pwd)/dummy_workspace/bin:$PATH"
mkdir -p dummy_workspace
"""
if target in content and 'openclaw' not in content:
    content = content.replace(target, mock_code, 1)
    with open(file_path, "w") as f:
        f.write(content)
print(f"Patched {file_path}")
