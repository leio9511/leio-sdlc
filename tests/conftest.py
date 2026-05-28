import os
import subprocess
from pathlib import Path
import pytest

PROJECT_ROOT = os.getcwd()
os.environ["SDLC_TEST_MODE"] = "true"

@pytest.fixture(autouse=True)
def global_restore_cwd():
    """Globally restore the current working directory after each test."""
    try:
        original_cwd = os.getcwd()
    except FileNotFoundError:
        original_cwd = PROJECT_ROOT
        
    yield
    try:
        os.chdir(original_cwd)
    except FileNotFoundError:
        os.chdir(PROJECT_ROOT)

def init_git_test_sandbox(target_dir: str | Path, baseline_commit: bool = False):
    """
    Initializes a local git repository to achieve clean-runner parity.
    Sets repo-local identity (user.name, user.email).
    Optionally creates an initial empty commit if baseline_commit is True.
    """
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    
    try:
        resolved_top = subprocess.check_output(
            ["git", "-C", str(target), "rev-parse", "--show-toplevel"], 
            stderr=subprocess.DEVNULL, 
            text=True
        ).strip()
        has_git = (str(target) == resolved_top)
    except subprocess.CalledProcessError:
        has_git = False
    if not has_git:
        subprocess.run(["git", "-C", str(target), "init", "-b", "master"], check=True, capture_output=True)

    subprocess.run(["git", "-C", str(target), "config", "--local", "user.name", "SDLC Test Sandbox"], check=True)
    subprocess.run(["git", "-C", str(target), "config", "--local", "user.email", "sdlc-test-sandbox@example.invalid"], check=True)
    
    if baseline_commit:
        has_commits = False
        try:
            subprocess.check_call(["git", "-C", str(target), "rev-parse", "--verify", "HEAD"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            has_commits = True
        except subprocess.CalledProcessError:
            has_commits = False
            
        if has_commits:
            return
            
        status = subprocess.check_output(
            ["git", "-C", str(target), "status", "--porcelain", "--untracked-files=no"],
            text=True
        )
        if status.strip():
            raise RuntimeError(f"Error: --baseline-commit requires a clean index in {target}")
            
        subprocess.run(["git", "-C", str(target), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)

@pytest.fixture
def git_test_sandbox():
    """Pytest fixture exposing init_git_test_sandbox."""
    return init_git_test_sandbox
