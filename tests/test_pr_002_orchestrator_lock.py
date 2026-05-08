import os
import subprocess
import time
import tempfile


def test_concurrent_orchestrator_blocked(git_test_sandbox):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orchestrator_path = os.path.join(project_root, "scripts", "orchestrator.py")
    doctor_path = os.path.join(project_root, "scripts", "doctor.py")

    with tempfile.TemporaryDirectory() as tmpdir:
        workdir = tmpdir
        git_test_sandbox(workdir, baseline_commit=True)
        subprocess.run(["python3", doctor_path, workdir, "--fix"], cwd=project_root, check=True, capture_output=True, text=True)

        # We start a background orchestrator that sleeps
        env = os.environ.copy()
        env["SDLC_BYPASS_BRANCH_CHECK"] = "1"
        env["SDLC_TEST_MODE"] = "true"

        # Start first instance
        proc1 = subprocess.Popen(
            ["python3", orchestrator_path, "--force-replan", "true", "--enable-exec-from-workspace", "--workdir", workdir, "--prd-file", "dummy", "--test-sleep"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=project_root
        )

        # Give it a moment to acquire the lock
        time.sleep(0.5)

        # Start second instance
        proc2 = subprocess.Popen(
            ["python3", orchestrator_path, "--force-replan", "true", "--enable-exec-from-workspace", "--workdir", workdir, "--prd-file", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=project_root
        )

        stdout2, stderr2 = proc2.communicate()
        output = stdout2.decode() + stderr2.decode()

        # Wait for the first one to finish
        proc1.terminate()
        proc1.communicate()

        assert proc2.returncode == 1
        assert "[FATAL] Another SDLC pipeline is currently running. Concurrent execution is blocked." in output
