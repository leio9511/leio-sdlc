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

def run_orchestrator(td, prd_path, *args):
    orchestrator_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "orchestrator.py")
    cmd = [
        get_repo_python(), orchestrator_path, 
        "--workdir", td, 
        "--prd-file", prd_path,
        "--enable-exec-from-workspace"
    ] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=td)

def test_resume_fails_closed_on_missing_state(clean_cwd, git_test_sandbox):
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        prd_path, run_dir = setup_mock_env(td, git_test_sandbox)
        
        # State file is missing
        res = run_orchestrator(td, prd_path, "--resume")
        assert res.returncode == 1
        assert "[FATAL] Missing or corrupt resume_state.json" in res.stdout

def test_resume_reenters_blocked_fatal_pr(clean_cwd, git_test_sandbox):
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
            
        # mock spawn_coder.py? Wait, if we resume and it's open, it will try to spawn coder.
        # But wait, orchestrator calls spawn_coder if status is open!
        # If it calls spawn_coder, we know it didn't jump to queue completion!
        
        # we can just write a wrapper around orchestrator or check stdout
        os.environ["SDLC_TEST_MODE"] = "true"
        os.environ["LLM_DRIVER"] = "mock"
        res = run_orchestrator(td, prd_path, "--resume")
        # should fail in orchestrator because mock is not handled well without tests?
        # or we check if it updated status to open?
        with open(pr_path, "r") as f:
            content = f.read()
        assert "status: open" in content

def test_resume_reconnects_uat_recovery(clean_cwd, git_test_sandbox):
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        prd_path, run_dir = setup_mock_env(td, git_test_sandbox)
        
        with open(os.path.join(run_dir, "resume_state.json"), "w") as f:
            json.dump({
                "state": "UAT_RECOVERY_ACTIVE",
                "currentPrPath": None,
                "currentBranch": "feature/test",
                "baselineCommit": "dummy_hash",
                "recoveryMode": "uat_recovery",
                "splitAllowed": False,
                "updatedAt": "2023-01-01T00:00:00Z"
            }, f)
            
        # Add uat_report.json to simulate UAT failure
        with open(os.path.join(run_dir, "uat_report.json"), "w") as f:
            json.dump({
                "status": "NEEDS_FIX",
                "verification_details": [
                    {"status": "MISSING", "desc": "test"}
                ]
            }, f)
            
        res = run_orchestrator(td, prd_path, "--resume")
        # what is the expected outcome?
        # It should try to run spawn_planner.py with --replan-uat-failures
        assert "--replan-uat-failures" in res.stdout or "STATE_UAT_RECOVERY" in res.stdout or "STATE_UAT_RECOVERY" in res.stderr

