import os
import subprocess
import tempfile
import pytest

import pytest


def test_independent_symmetrical_rollbacks():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        
        # 1. Run first deployment
        deploy_script = os.path.join(repo_root, "kit-deploy.sh")
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"First kit-deploy.sh failed: {res.stderr}"

        # 2. Run second deployment to create the backup archives of the first installation
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Second kit-deploy.sh failed: {res.stderr}"
        
        # Modify installed files slightly to verify rollback overwrites them
        skills_dir = os.path.join(mock_home, ".openclaw", "skills")
        for skill in ["leio-sdlc", "pm-skill"]:
            skill_path = os.path.join(skills_dir, skill)
            marker = os.path.join(skill_path, "MODIFIED_MARKER")
            with open(marker, "w") as f:
                f.write("modified")
                
        # 3. Run rollbacks
        scripts = [
            ("leio-sdlc", os.path.join(repo_root, "scripts", "rollback.sh")),
            ("pm-skill", os.path.join(repo_root, "skills", "pm-skill", "rollback.sh")),
            
        ]
        
        for skill_name, script_path in scripts:
            assert os.path.exists(script_path), f"{script_path} does not exist"
            # Ensure --no-restart is supported and runs successfully
            res = subprocess.run(["bash", script_path, "--no-restart"], env=env, cwd=repo_root, capture_output=True, text=True)
            assert res.returncode == 0, f"Rollback failed for {skill_name}:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            
            # Verify marker is gone (rollback replaced the directory from tarball)
            skill_path = os.path.join(skills_dir, skill_name)
            marker = os.path.join(skill_path, "MODIFIED_MARKER")
            assert not os.path.exists(marker), f"Rollback did not restore {skill_name} cleanly (marker still exists)"
            
            # Ensure basic structure exists
            if skill_name == "leio-sdlc":
                assert os.path.exists(os.path.join(skill_path, "scripts", "orchestrator.py"))
            elif skill_name == "pm-skill":
                assert os.path.exists(os.path.join(skill_path, "scripts", "init_prd.py"))            

def test_rollback_no_restart_with_mock():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        
        # 1. Run first deployment
        deploy_script = os.path.join(repo_root, "kit-deploy.sh")
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"kit-deploy.sh failed: {res.stderr}"

        # 2. Run second deployment to create the backup
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Second kit-deploy.sh failed: {res.stderr}"
        
        # 3. Run rollback
        script_path = os.path.join(repo_root, "scripts", "rollback.sh")
        res = subprocess.run(["bash", script_path], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Rollback failed: {res.stderr}"
        
        # Verify that it skipped restarting OpenClaw
        assert "Skipping OpenClaw gateway restart (mock environment detected)..." in res.stdout, "Gateway restart was not skipped"

def test_rollback_lock_guardrails():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        
        # 1. Setup mock installation
        skills_dir = os.path.join(mock_home, ".openclaw", "skills")
        os.makedirs(skills_dir, exist_ok=True)
        leio_sdlc_dir = os.path.join(skills_dir, "leio-sdlc")
        os.makedirs(leio_sdlc_dir, exist_ok=True)
        
        releases_dir = os.path.join(mock_home, ".openclaw", ".releases", "leio-sdlc")
        os.makedirs(releases_dir, exist_ok=True)
        # Create a dummy backup
        subprocess.run(["tar", "-czf", os.path.join(releases_dir, "backup_20230101_000000.tar.gz"), "-C", skills_dir, "leio-sdlc"])
        
        rollback_script = os.path.join(repo_root, "scripts", "rollback.sh")
        
        # Test each lock file
        for lock_file in [".sdlc_repo.lock", ".coder_session", ".sdlc_lock_manifest.json"]:
            lock_path = os.path.join(leio_sdlc_dir, lock_file)
            with open(lock_path, "w") as f:
                f.write("locked")
            
            res = subprocess.run(["bash", rollback_script, "--no-restart"], env=env, cwd=leio_sdlc_dir, capture_output=True, text=True)
            assert res.returncode != 0, f"Rollback should have failed due to {lock_file}"
            assert "[FATAL_LOCK] Cannot rollback while another SDLC pipeline is active" in res.stdout
            
            os.remove(lock_path)
