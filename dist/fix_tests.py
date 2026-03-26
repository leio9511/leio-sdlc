import os
import glob
import re

def replace_in_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    # Replace literal file writes
    new_content = content.replace('f.write("[LGTM]\\n")', 'f.write(\'```json\\n{"status": "APPROVED", "comments": "OK"}\\n```\\n\')')
    new_content = new_content.replace('f.write('```json\n{"status": "APPROVED", "comments": "OK"}\n```\n')', 'f.write(\'```json\\n{"status": "APPROVED", "comments": "OK"}\\n```\\n\')')
    
    # Replace grep checks
    new_content = new_content.replace('grep -qi "\\[LGTM\\]"', 'grep -qi "APPROVED"')
    new_content = new_content.replace('grep -q "\\[LGTM\\]"', 'grep -q "APPROVED"')
    new_content = new_content.replace('did not output APPROVED', 'did not output APPROVED')
    
    # Replace python string assertions
    new_content = new_content.replace('self.assertIn("APPROVED", content)', 'self.assertIn("APPROVED", content)')
    
    if content != new_content:
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"Patched {filepath}")

for root, _, files in os.walk("/root/.openclaw/workspace/projects/leio-sdlc"):
    if "venv" in root or "__pycache__" in root or ".git" in root: continue
    for file in files:
        if file.endswith(".sh") or file.endswith(".py"):
            replace_in_file(os.path.join(root, file))
