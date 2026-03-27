import os
import glob

def patch_test(file_path):
    with open(file_path, "r") as f:
        content = f.read()
    
    # Check if openclaw mock is already added
    if 'mkdir -p "bin"' in content and 'openclaw' in content:
        return
        
    if 'setup_sandbox()' in content:
        # Patch setup_sandbox
        target = '    sandbox_dir=$(mktemp -d)\n    cd "$sandbox_dir"\n'
        mock_code = """    sandbox_dir=$(mktemp -d)
    cd "$sandbox_dir"
    mkdir -p "bin"
    cat << 'INNER_EOF' > "bin/openclaw"
#!/bin/bash
exit 0
INNER_EOF
    chmod +x "bin/openclaw"
    export PATH="$(pwd)/bin:$PATH"
"""
        if target in content:
            content = content.replace(target, mock_code)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"Patched {file_path}")

for f in glob.glob("scripts/*.sh"):
    patch_test(f)
