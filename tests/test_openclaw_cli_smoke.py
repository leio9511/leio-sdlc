import unittest
import subprocess
import shutil
import os

class TestOpenClawCLISmoke(unittest.TestCase):
    def setUp(self):
        # Filter out mock_bin from PATH to ensure we are testing the REAL CLI
        original_path = os.environ.get("PATH", "")
        paths = original_path.split(os.pathsep)
        filtered_paths = [p for p in paths if "mock_bin" not in p]
        self.clean_env = os.environ.copy()
        self.clean_env["PATH"] = os.pathsep.join(filtered_paths)
        
        # Also find the real openclaw
        self.real_openclaw = shutil.which("openclaw", path=self.clean_env["PATH"])

    def test_openclaw_binary_exists(self):
        self.assertIsNotNone(self.real_openclaw, "REAL openclaw binary not found in cleaned PATH")

    def test_openclaw_agents_list_format(self):
        # This test ensures that the output of 'openclaw agents list' 
        # follows the expected human-readable format that our parser handles.
        res = subprocess.run([self.real_openclaw, "agents", "list"], capture_output=True, text=True, env=self.clean_env)
        self.assertEqual(res.returncode, 0)
        
        # We expect it to contain "Agents:" or "No agents" but not "Unknown"
        # If no agents exist, it returns "No agents"
        # If agents exist, it contains "Agents:"
        self.assertTrue("Agents:" in res.stdout or "No agents" in res.stdout)
        
    def test_openclaw_agents_show_does_not_exist(self):
        # Negative test to confirm our finding that 'agents show' is indeed unsupported
        res = subprocess.run([self.real_openclaw, "agents", "show", "non-existent-agent"], capture_output=True, text=True, env=self.clean_env)
        self.assertNotEqual(res.returncode, 0)
        # Error message might vary, but it definitely shouldn't be empty if it fails due to unknown command
        # or it should contain "too many arguments" or "unknown command"
        error_msg = (res.stderr + res.stdout).lower()
        self.assertTrue("too many arguments" in error_msg or "unknown command" in error_msg or "show" not in error_msg)

    def test_openclaw_gateway_restart_command_exists(self):
        # Verify that 'gateway restart' is a valid subcommand
        res = subprocess.run([self.real_openclaw, "gateway", "--help"], capture_output=True, text=True, env=self.clean_env)
        self.assertEqual(res.returncode, 0)
        self.assertIn("restart", res.stdout)

if __name__ == "__main__":
    unittest.main()
