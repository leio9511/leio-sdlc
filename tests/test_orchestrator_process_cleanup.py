import os
import sys
import time
import signal
import pytest
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator

def test_dpopen_tracks_pid(tmp_path):
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    proc = None
    try:
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        proc = orchestrator.dpopen(cmd, start_new_session=True)
        
        pids_file = tmp_path / ".sdlc_runs" / "pids" / "sdlc_pids.txt"
        assert pids_file.exists(), "PIDs file was not created"
        
        content = pids_file.read_text().strip()
        assert str(proc.pid) in content.split("\n"), f"PID {proc.pid} not found in {content}"
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait()
            except Exception:
                pass
        os.chdir(orig_cwd)

def test_cleanup_tracked_processes_reaps_and_wipes(tmp_path):
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    proc = subprocess.Popen(cmd, start_new_session=True)
    
    try:
        pids_dir = tmp_path / ".sdlc_runs" / "pids"
        pids_dir.mkdir(parents=True, exist_ok=True)
        pids_file = pids_dir / "sdlc_pids.txt"
        pids_file.write_text(f"{proc.pid}\n")
        
        # Verify process is running
        os.kill(proc.pid, 0)
        
        # Call cleanup
        orchestrator.cleanup_tracked_processes(str(tmp_path))
        
        # Verify process is terminated
        time.sleep(0.5)
        proc.poll() # Reap the zombie process since we are the parent
        with pytest.raises(OSError):
            os.kill(proc.pid, 0)
            
        # Verify file is deleted
        assert not pids_file.exists(), "PIDs file was not deleted"
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()

if __name__ == '__main__':
    pytest.main([__file__])
