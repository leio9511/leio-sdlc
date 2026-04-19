import re
import os

VALID_STATES = {"open", "in_progress", "closed", "blocked"}

def get_status(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find frontmatter bounds
    match = re.search(r'^---\s*\n(.*?)\n---\s*(?:\n|$)', content, re.DOTALL)
    if not match:
        raise ValueError("No valid YAML frontmatter found")

    frontmatter = match.group(1)
    status_match = re.search(r'^status:\s*(\w+)', frontmatter, re.MULTILINE)
    
    if not status_match:
        raise ValueError("No status field found in frontmatter")
        
    status = status_match.group(1)
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
        raise ValueError("No valid YAML frontmatter found")

    frontmatter = match.group(1)
    
    if not re.search(r'^status:\s*\w+', frontmatter, re.MULTILINE):
        raise ValueError("No status field found in frontmatter")
        
    updated_frontmatter = re.sub(r'^status:\s*\w+', f'status: {new_status}', frontmatter, count=1, flags=re.MULTILINE)
    
    # Replace the exact frontmatter back into the content
    # We use string slicing to avoid regex replacement issues with special characters in content
    start = match.start(1)
    end = match.end(1)
    updated_content = content[:start] + updated_frontmatter + content[end:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(updated_content)

