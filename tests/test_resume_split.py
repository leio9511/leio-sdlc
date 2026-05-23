import os
from tests.python_contract_support import get_repo_python
import subprocess
import tempfile
import json
import pytest

@pytest.fixture
def clean_cwd():
    orig_cwd = os.getcwd()
    yield
    os.chdir(orig_cwd)

def setup_mock_env(td, git_test_sandbox):
    git_test_sandbox(td, baseline_commit=True)
    import subprocess
    doctor_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "doctor.py")
    subprocess.run([get_repo_python(), doctor_path, td, "--fix"], check=True)
    subprocess.run(["git", "checkout", "-b", "feature/test"], check=True)
    
    prd_path = os.path.join(td, "docs", "PRDs", "PRD_Test.md")
    os.makedirs(os.path.dirname(prd_path), exist_ok=True)
    with open(prd_path, "w") as f:
        f.write("# dummy")
        
    run_dir = os.path.join(td, ".sdlc_runs", os.path.basename(td), "PRD_Test")
    os.makedirs(run_dir, exist_ok=True)
    
    with open(os.path.join(run_dir, "baseline_commit.txt"), "w") as f:
        f.write("dummy_hash")
        
    with open(os.path.join(run_dir, "run_manifest.json"), "w") as f:
        json.dump({
            "baseline_commit": "dummy_hash",
            "prd_path": prd_path,
            "job_dir": run_dir,
            "run_dir": run_dir,
            "started_at": "2023-01-01T00:00:00Z"
        }, f)
        
    return prd_path, run_dir

def run_orchestrator(td, prd_path, env=None, *args):
    orchestrator_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "orchestrator.py")
    cmd = [
        get_repo_python(), orchestrator_path, 
        "--workdir", td, 
        "--prd-file", prd_path,
        "--enable-exec-from-workspace"
    ] + list(args)
    if env is None:
        env = os.environ.copy()
    return subprocess.run(cmd, capture_output=True, text=True, cwd=td, env=env)

def test_resume_split_fails_when_not_allowed(clean_cwd, git_test_sandbox):
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        prd_path, run_dir = setup_mock_env(td, git_test_sandbox)
        
        pr_path = os.path.join(run_dir, "PR_001_Test.md")
        with open(pr_path, "w") as f:
            f.write("---\nstatus: blocked_fatal\n---\n# test")
            
        with open(os.path.join(run_dir, "resume_state.json"), "w") as f:
            json.dump({
                "state": "CODER_ACTIVE",
                "currentPrPath": pr_path,
                "currentBranch": "feature/test",
                "baselineCommit": "dummy_hash",
                "recoveryMode": "mainline",
                "splitAllowed": False,
                "updatedAt": "2023-01-01T00:00:00Z"
            }, f)
            
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        
        res = run_orchestrator(td, prd_path, env, "--split")
        assert res.returncode == 1
        assert "[FATAL] --split validation failed: Current state does not permit split or no authoritative active PR found." in res.stdout

def test_resume_split_supersedes_pr_and_updates_state(clean_cwd, git_test_sandbox):
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        prd_path, run_dir = setup_mock_env(td, git_test_sandbox)
        
        pr_path = os.path.join(run_dir, "PR_001_Test.md")
        with open(pr_path, "w") as f:
            f.write("---\nstatus: blocked_fatal\n---\n# test")
            
        with open(os.path.join(run_dir, "resume_state.json"), "w") as f:
            json.dump({
                "state": "CODER_ACTIVE",
                "currentPrPath": pr_path,
                "currentBranch": "feature/test",
                "baselineCommit": "dummy_hash",
                "recoveryMode": "mainline",
                "splitAllowed": True,
                "updatedAt": "2023-01-01T00:00:00Z"
            }, f)
            
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        env["LLM_DRIVER"] = "mock" # just in case
        
        res = run_orchestrator(td, prd_path, env, "--split")
        
        # Depending on if orchestrator exits normally or keeps running.
        # But split normally just returns to the planner or completes.
        # It calls sys.exit(0) at the end of orchestrator? Or falls through?
        # Let's verify the file contents.
        with open(pr_path, "r") as f:
            pr_content = f.read()
        assert "status: superseded" in pr_content
        
        with open(os.path.join(run_dir, "resume_state.json"), "r") as f:
            state_data = json.load(f)
            
        assert state_data["recoveryMode"] == "split"
        assert state_data["splitAllowed"] is False
        assert state_data["state"] == "PLANNER_ACTIVE"

def test_resume_split_fails_when_missing_state(clean_cwd, git_test_sandbox):
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        prd_path, run_dir = setup_mock_env(td, git_test_sandbox)
        
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        
        res = run_orchestrator(td, prd_path, env, "--split")
        assert res.returncode == 1
        assert "[FATAL] Missing or corrupt resume_state.json. Cannot resume safely." in res.stdout
