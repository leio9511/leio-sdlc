import os
import subprocess
import tempfile
import time
import fcntl
import json

def test_cleanup_quarantine():
    with tempfile.TemporaryDirectory() as global_dir, tempfile.TemporaryDirectory() as td:
        # Override the global lock dir for tests
        os.environ["HOME"] = global_dir  # ~ points to global_dir
        lock_dir = os.path.expanduser("~/.openclaw/workspace/locks")
        os.makedirs(lock_dir, exist_ok=True)
        
        orig_dir = os.getcwd()
        try:
            orig_dir = os.getcwd()
        try:
            os.chdir(td)
        subprocess.run(["git", "init"], check=True)
        subprocess.run(["git", "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], check=True)
        
        # Create a branch and a dirty file
        subprocess.run(["git", "checkout", "-b", "feature/toxic_branch"], check=True)
        with open("dirty.txt", "w") as f:
            f.write("bad code")
        
        # Create dummy locks
        with open(".sdlc_repo.lock", "w") as f:
            f.write("locked")
        with open(".coder_session", "w") as f:
            f.write("session123")
            
        dummy_lock_1 = os.path.join(td, "dummy1.lock")
        dummy_lock_2 = os.path.join(td, "dummy2.lock")
        with open(dummy_lock_1, "w") as f:
            f.write("locked")
        with open(dummy_lock_2, "w") as f:
            f.write("locked")
            
        with open(".sdlc_lock_manifest.json", "w") as f:
            json.dump({"locks": [dummy_lock_1, dummy_lock_2]}, f)
            
        # Create a global lock file with DEAD PID
        dead_pid = 999999
        global_lock = os.path.join(lock_dir, "test_project.lock")
        with open(global_lock, "w") as f:
            json.dump({"pid": dead_pid, "active_workdir": td}, f)
            
        # Run orchestrator cleanup
        orchestrator_path = "/root/.openclaw/workspace/projects/leio-sdlc/scripts/orchestrator.py"
        res = subprocess.run([
            "python3", orchestrator_path, 
            "--cleanup",
            "--enable-exec-from-workspace"
        ], capture_output=True, text=True, env=os.environ)
        
        assert res.returncode == 0, f"Cleanup failed: {res.stderr}"
        
        # Assertions
        orig_dir = os.getcwd()
        try:
            orig_dir = os.getcwd()
        try:
            os.chdir(td)
        # 1. Master is checked out
        current_branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        assert current_branch == "master", f"Branch is {current_branch}, expected master"
        
        # 2. Toxic branch was renamed
        branches = subprocess.run(["git", "branch"], capture_output=True, text=True).stdout
        assert "feature/toxic_branch_crashed_" in branches
        assert "feature/toxic_branch " not in branches
        
        # 3. Locks deleted
        assert not os.path.exists(".sdlc_repo.lock")
        assert not os.path.exists(".coder_session")
        assert not os.path.exists(dummy_lock_1)
        assert not os.path.exists(dummy_lock_2)
        assert not os.path.exists(".sdlc_lock_manifest.json")
        assert not os.path.exists(global_lock)

        finally:
            os.chdir(orig_dir)

def test_cleanup_lock_blocked():
    with tempfile.TemporaryDirectory() as global_dir, tempfile.TemporaryDirectory() as td:
        os.environ["HOME"] = global_dir  # ~ points to global_dir
        lock_dir = os.path.expanduser("~/.openclaw/workspace/locks")
        os.makedirs(lock_dir, exist_ok=True)
        
        # Alive pid
        alive_pid = os.getpid()
        global_lock = os.path.join(lock_dir, "test_project.lock")
        with open(global_lock, "w") as f:
            json.dump({"pid": alive_pid, "active_workdir": td}, f)
            
        orig_dir = os.getcwd()
        try:
            orig_dir = os.getcwd()
        try:
            os.chdir(td)
        with open(".sdlc_repo.lock", "w") as f:
            f.write("locked")
            
        orchestrator_path = "/root/.openclaw/workspace/projects/leio-sdlc/scripts/orchestrator.py"
        res = subprocess.run([
            "python3", orchestrator_path, 
            "--cleanup",
            "--enable-exec-from-workspace"
        ], capture_output=True, text=True, env=os.environ)
        
        # Should skip because pid is alive
        assert res.returncode == 0
        assert os.path.exists(global_lock)
        assert os.path.exists(".sdlc_repo.lock")
        
        finally:
            os.chdir(orig_dir)

if __name__ == "__main__":
    test_cleanup_quarantine()
    test_cleanup_lock_blocked()
    print("Cleanup tests passed.")
