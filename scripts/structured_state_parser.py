import re
import os
import yaml

VALID_STATES = {"open", "in_progress", "closed", "blocked", "blocked_fatal", "superseded"}

def get_status(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find frontmatter bounds
    match = re.search(r'^---\s*\n(.*?)\n---\s*(?:\n|$)', content, re.DOTALL)
    if not match:
        raise ValueError(f"[FATAL_FORMAT] No valid YAML frontmatter delimiters (---) found in file: {os.path.abspath(file_path)}")

    frontmatter = match.group(1)
    
    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError as e:
        raise ValueError(f"[FATAL_FORMAT] YAML syntax error in frontmatter: {str(e)} at {os.path.abspath(file_path)}")
        
    if not isinstance(data, dict) or 'status' not in data:
        raise ValueError("No status field found in frontmatter")
        
    status = data['status']
    if status not in VALID_STATES:
        raise ValueError(f"Invalid status: {status}. Must be one of {VALID_STATES}")
        
    return status

def update_status(file_path, new_status):
    if new_status not in VALID_STATES:
        raise ValueError(f"Invalid new status: {new_status}. Must be one of {VALID_STATES}")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    match = re.search(r'^---\s*\n(.*?)\n---\s*(?:\n|$)', content, re.DOTALL)
    if not match:
        raise ValueError(f"[FATAL_FORMAT] No valid YAML frontmatter delimiters (---) found in file: {os.path.abspath(file_path)}")

    frontmatter = match.group(1)
    
    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError as e:
        raise ValueError(f"[FATAL_FORMAT] YAML syntax error in frontmatter: {str(e)} at {os.path.abspath(file_path)}")
    
    if not isinstance(data, dict) or 'status' not in data:
        raise ValueError("No status field found in frontmatter")
        
    # Replace the exact frontmatter back into the content
    # We use string replacement to avoid regex issues, though re.sub is also okay if it doesn't break formatting.
    updated_frontmatter = re.sub(r'^status:\s*\w+', f'status: {new_status}', frontmatter, count=1, flags=re.MULTILINE)
    
    start = match.start(1)
    end = match.end(1)
    updated_content = content[:start] + updated_frontmatter + content[end:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)
