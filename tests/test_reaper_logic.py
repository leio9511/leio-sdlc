import os
import subprocess
import signal
import time
import sys
import pytest

def test_reaper(tmp_path):
    test_script = tmp_path / "reaper_dummy.py"
    test_script.write_text("""import os
import subprocess
import signal
import time
import sys

def run_isolated_child():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"], start_new_session=True)

proc = None
try:
    proc = run_isolated_child()
    print(f"CHILD_PID:{proc.pid}")
    sys.stdout.flush()
    raise KeyboardInterrupt
finally:
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            pass
""")

    proc = subprocess.Popen([sys.executable, str(test_script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        pytest.fail("Test script hung and had to be killed.")
    
    child_pid = None
    for line in out.splitlines():
        if "CHILD_PID:" in line:
            child_pid = int(line.split(":")[1])
    
    assert child_pid is not None, "Could not determine child PID."
    
    time.sleep(0.5)
    try:
        os.kill(child_pid, 0)
        pytest.fail(f"Child process {child_pid} still alive.")
    except OSError:
        pass  # Process is reaped successfully

if __name__ == '__main__':
    pytest.main([__file__])
