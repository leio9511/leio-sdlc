import os
import sys
import tempfile
import subprocess
import shutil
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

def run_git(cmd, cwd):
    return subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True, check=True)

@pytest.fixture
def repo_env(tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    
    run_git(["init"], cwd=workdir)
    (workdir / "file.txt").write_text("v1")
    run_git(["add", "file.txt"], cwd=workdir)
    run_git(["commit", "-m", "init"], cwd=workdir)
    run_git(["branch", "-m", "master"], cwd=workdir)
    
    baseline_hash = run_git(["rev-parse", "HEAD"], cwd=workdir).stdout.strip()
    
    global_dir = tmp_path / "global"
    global_dir.mkdir()
    
    prd_name = "PRD_Test"
    project_name = "workdir"
    
    job_dir = global_dir / ".sdlc_runs" / project_name / prd_name
    job_dir.mkdir(parents=True)
    
    (job_dir / "baseline_commit.txt").write_text(baseline_hash)
    
    return {
        "workdir": str(workdir),
        "global_dir": str(global_dir),
        "job_dir": str(job_dir),
        "prd_name": prd_name,
        "baseline_hash": baseline_hash
    }

def run_orchestrator_withdraw(workdir, global_dir, prd_name, capture=True):
    import orchestrator
    import argparse
    from unittest.mock import patch
    
    args = [
        "orchestrator.py",
        "--workdir", workdir,
        "--prd-file", f"{prd_name}.md",
        "--global-dir", global_dir,
        "--withdraw",
        "--enable-exec-from-workspace",
    ]
    with patch.object(sys, "argv", args):
        try:
            orchestrator.main()
        except SystemExit as e:
            if e.code != 0:
                raise RuntimeError(f"Orchestrator exited with {e.code}")

def test_withdraw_baseline_alignment(repo_env, capsys):
    workdir = repo_env["workdir"]
    
    # Introduce some changes and commit
    with open(os.path.join(workdir, "file.txt"), "w") as f:
        f.write("v2")
    run_git(["add", "file.txt"], cwd=workdir)
    run_git(["commit", "-m", "interrupted WIP"], cwd=workdir)
    
    run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    # Verify we committed the alignment
    log = run_git(["log", "-n", "1", "--oneline"], cwd=workdir).stdout
    assert "chore: force baseline alignment of PRD" in log
    
    # Verify working tree is aligned to v1 (baseline)
    with open(os.path.join(workdir, "file.txt"), "r") as f:
        assert f.read() == "v1"

def test_withdraw_idempotency(repo_env):
    workdir = repo_env["workdir"]
    
    # First withdraw (no changes from baseline, just tearing down)
    run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    assert os.path.exists(repo_env["job_dir"] + ".withdrawn")
    
    # Second withdraw
    run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    # No crashes means success. It should have just printed [INFO] ignoring.

def test_withdraw_governance_warning(repo_env, capfd):
    workdir = repo_env["workdir"]
    
    # Add a non-SDLC commit
    with open(os.path.join(workdir, "extra.txt"), "w") as f:
        f.write("unauthorized")
    run_git(["add", "extra.txt"], cwd=workdir)
    run_git(["commit", "-m", "unauthorized external commit"], cwd=workdir)
    
    run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    out, err = capfd.readouterr()
    assert "[WARNING] Unauthorized external commits detected" in out

def test_withdraw_job_teardown(repo_env):
    workdir = repo_env["workdir"]
    job_dir = repo_env["job_dir"]
    
    assert os.path.exists(job_dir)
    run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    assert not os.path.exists(job_dir)
    assert os.path.exists(job_dir + ".withdrawn")


@pytest.fixture
def repo_env_main(tmp_path):
    workdir = tmp_path / "workdir_main"
    workdir.mkdir()
    
    run_git(["init"], cwd=workdir)
    (workdir / "file.txt").write_text("v1")
    run_git(["add", "file.txt"], cwd=workdir)
    run_git(["commit", "-m", "init"], cwd=workdir)
    run_git(["branch", "-m", "main"], cwd=workdir)
    
    baseline_hash = run_git(["rev-parse", "HEAD"], cwd=workdir).stdout.strip()
    
    global_dir = tmp_path / "global_main"
    global_dir.mkdir()
    
    prd_name = "PRD_Test_Main"
    project_name = "workdir_main"
    
    job_dir = global_dir / ".sdlc_runs" / project_name / prd_name
    job_dir.mkdir(parents=True)
    
    (job_dir / "baseline_commit.txt").write_text(baseline_hash)
    
    return {
        "workdir": str(workdir),
        "global_dir": str(global_dir),
        "job_dir": str(job_dir),
        "prd_name": prd_name,
        "baseline_hash": baseline_hash
    }

def test_withdraw_baseline_alignment_main(repo_env_main, capsys):
    workdir = repo_env_main["workdir"]
    
    # Switch to feature branch
    run_git(["checkout", "-b", "feature_branch"], cwd=workdir)
    
    # Introduce some changes and commit
    with open(os.path.join(workdir, "file.txt"), "w") as f:
        f.write("v2")
    run_git(["add", "file.txt"], cwd=workdir)
    run_git(["commit", "-m", "interrupted WIP"], cwd=workdir)
    
    run_orchestrator_withdraw(workdir, repo_env_main["global_dir"], repo_env_main["prd_name"])
    
    # Verify working tree is aligned to v1 (baseline)
    with open(os.path.join(workdir, "file.txt"), "r") as f:
        assert f.read() == "v1"

    # Current branch should be main
    branch = run_git(["branch", "--show-current"], cwd=workdir).stdout.strip()
    assert branch == "main"

def test_withdraw_missing_metadata(repo_env, capfd):
    workdir = repo_env["workdir"]
    job_dir = repo_env["job_dir"]
    
    # Remove metadata
    baseline_file = os.path.join(job_dir, "baseline_commit.txt")
    if os.path.exists(baseline_file):
        os.remove(baseline_file)
        
    with pytest.raises(RuntimeError) as excinfo:
        run_orchestrator_withdraw(workdir, repo_env["global_dir"], repo_env["prd_name"])
    
    assert "Orchestrator exited with 1" in str(excinfo.value)
    out, err = capfd.readouterr()
    assert "Handoff_Metadata_Missing" in out

