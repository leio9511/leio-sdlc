import os
import subprocess
import pytest
import sys

def test_commit_state_rejects_source_code(tmp_path):
    # Setup mock git repo
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    
    with open("main.py", "w") as f:
        f.write("print('hello')")
        
    script_path = "/root/.openclaw/workspace/projects/leio-sdlc/scripts/commit_state.py"
    
    # Try to commit source code
    result = subprocess.run(["python3", script_path, "--files", "main.py"], capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "[FATAL] commit_state.py can only be used for state and PRD files. Source code changes must go through the SDLC pipeline." in result.stdout

def test_commit_state_success(tmp_path):
    # Setup mock git repo
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    subprocess.run(["git", "config", "user.email", "test@example.com"])
    subprocess.run(["git", "config", "user.name", "Test User"])
    
    os.makedirs("docs/PRDs", exist_ok=True)
    
    with open("STATE.md", "w") as f:
        f.write("state")
        
    with open("docs/PRDs/PRD_001_Test.md", "w") as f:
        f.write("prd")
        
    script_path = "/root/.openclaw/workspace/projects/leio-sdlc/scripts/commit_state.py"
    
    # Commit state files
    result = subprocess.run(["python3", script_path, "--files", "STATE.md", "docs/PRDs/PRD_001_Test.md"], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "Successfully baselined PRD/state files." in result.stdout

def test_commit_state_git_lock_error(tmp_path):
    # Setup mock git repo
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    
    with open("STATE.md", "w") as f:
        f.write("state")
        
    # Create fake lock file
    os.makedirs(".git", exist_ok=True)
    with open(".git/index.lock", "w") as f:
        f.write("")
        
    script_path = "/root/.openclaw/workspace/projects/leio-sdlc/scripts/commit_state.py"
    
    # Try to commit with lock file present
    result = subprocess.run(["python3", script_path, "--files", "STATE.md"], capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "[FATAL] Git index is locked. Please wait or remove .git/index.lock if a previous process crashed." in result.stdout
