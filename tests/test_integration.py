import unittest
import subprocess
import time
import os
import sys

class TestOrchestratorLock(unittest.TestCase):
    def test_concurrent_execution(self):
        env = os.environ.copy()
        env["SDLC_BYPASS_BRANCH_CHECK"] = "1"
        cmd = [sys.executable, "scripts/orchestrator.py", "--debug", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--test-sleep"]
        proc1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        time.sleep(0.5)
        proc2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        self.assertEqual(proc2.returncode, 1)
        expected_msg = "[FATAL] Another SDLC pipeline is currently running. Concurrent execution is blocked."
        self.assertIn(expected_msg, proc2.stdout)
        proc1.terminate()
        proc1.wait()
        proc1.stdout.close()
        proc1.stderr.close()
        if os.path.exists(".sdlc_repo.lock"):
            os.remove(".sdlc_repo.lock")

    def test_branch_check(self):
        # Without bypass, should fail
        env = os.environ.copy()
        if "SDLC_BYPASS_BRANCH_CHECK" in env:
            del env["SDLC_BYPASS_BRANCH_CHECK"]
        cmd = [sys.executable, "scripts/orchestrator.py", "--debug", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--test-sleep"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        # Since we are on a feature branch, it should exit with 1
        self.assertEqual(proc.returncode, 1)
        expected_msg = "[FATAL] Orchestrator must be started from the master or main branch."
        self.assertIn(expected_msg, proc.stdout)

if __name__ == '__main__':
    unittest.main()
