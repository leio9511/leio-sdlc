import os
import subprocess
import pytest
import sys
from unittest.mock import patch

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))
import config
import commit_state


def test_commit_state_validates_files(tmp_path):
    # Setup mock git repo
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    
    with open("main.py", "w") as f:
        f.write("print('hello')")
        
    script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/commit_state.py"
    
    # Try to commit source code
    result = subprocess.run(["python3", script_path, "--files", "main.py"], capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "[FATAL] commit_state.py can only be used for state and PRD files. Source code changes must go through the SDLC pipeline." in result.stdout

def test_orchestrator_rejects_uncommitted_state(tmp_path):
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    doctor_script = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/doctor.py"
    subprocess.run(["python3", doctor_script, str(tmp_path), "--fix"])
    with open("PRD_uncommitted.md", "w") as f:
        f.write("uncommitted")
        
    orchestrator_script = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/orchestrator.py"
    result = subprocess.run(["python3", orchestrator_script, "--enable-exec-from-workspace", "--workdir", str(tmp_path), "--prd-file", "PRD_uncommitted.md", "--force-replan", "true"], capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "Workspace contains uncommitted state files." in result.stdout
    assert f"python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py" in result.stdout

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

    with patch("commit_state.run_runtime_git") as mock_run_runtime_git:
        with patch.object(sys, "argv", ["commit_state.py", "--files", "STATE.md", "docs/PRDs/PRD_001_Test.md"]):
            commit_state.main()

    mock_run_runtime_git.assert_called_once_with(
        "commit_state",
        ["commit", "-m", "chore(state): update manager state"],
        check=True,
    )


def test_commit_state_uses_runtime_helper_with_commit_state_role(tmp_path):
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    subprocess.run(["git", "config", "user.email", "test@example.com"])
    subprocess.run(["git", "config", "user.name", "Test User"])

    with open("STATE.md", "w") as f:
        f.write("state")

    with patch("commit_state.run_runtime_git") as mock_run_runtime_git:
        with patch.object(sys, "argv", ["commit_state.py", "--files", "STATE.md"]):
            commit_state.main()

    mock_run_runtime_git.assert_called_once_with(
        "commit_state",
        ["commit", "-m", "chore(state): update manager state"],
        check=True,
    )

def test_pre_commit_hook_output(tmp_path):
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    subprocess.run(["git", "config", "user.email", "test@example.com"])
    subprocess.run(["git", "config", "user.name", "Test User"])
    
    with open(".sdlc_guardrail", "w") as f:
        f.write("")
        
    subprocess.run(["git", "add", ".sdlc_guardrail"])
    subprocess.run(["git", "commit", "-m", "init"])
    
    os.makedirs(".sdlc_hooks", exist_ok=True)
    subprocess.run(["cp", os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/.sdlc_hooks/pre-commit", ".sdlc_hooks/"])
    subprocess.run(["git", "config", "core.hooksPath", ".sdlc_hooks"])
    
    with open("test.txt", "w") as f:
        f.write("test")
    subprocess.run(["git", "add", "test.txt"])
    
    env = os.environ.copy()
    env["SDLC_SKILLS_ROOT"] = config.SDLC_SKILLS_ROOT
    result = subprocess.run(["git", "commit", "-m", "test"], capture_output=True, text=True, env=env)
    
    assert result.returncode == 1
    assert f"python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py --files <path_to_files>" in result.stdout or f"python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py --files <path_to_files>" in result.stderr

    # Verify runtime administrative commit succeeds through the role-aware policy
    with open("test2.txt", "w") as f:
        f.write("test2")
    subprocess.run(["git", "add", "test2.txt"])
    result_runtime = subprocess.run(
        [
            "git",
            "-c", "sdlc.runtime=1",
            "-c", "sdlc.role=commit_state",
            "commit", "-m", "chore(state): runtime admin commit",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result_runtime.returncode == 0, (
        f"Runtime administrative commit with commit_state role failed: "
        f"{result_runtime.stdout + result_runtime.stderr}"
    )

    # Setup mock git repo
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    
    with open("STATE.md", "w") as f:
        f.write("state")
        
    # Create fake lock file
    os.makedirs(".git", exist_ok=True)
    with open(".git/index.lock", "w") as f:
        f.write("")
        
    script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/commit_state.py"
    
    # Try to commit with lock file present
    result = subprocess.run(["python3", script_path, "--files", "STATE.md"], capture_output=True, text=True)
    
    assert result.returncode == 1
    assert "[FATAL] Git index is locked. Please wait or remove .git/index.lock if a previous process crashed." in result.stdout
