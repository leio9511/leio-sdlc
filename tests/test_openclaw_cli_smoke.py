import os
import subprocess
import shutil
import unittest
import pytest

class TestOpenClawCLISmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We need the REAL openclaw, not the one in mock_bin which might have been injected into PATH
        # by other tests (like test_078).
        current_path = os.environ.get("PATH", "").split(os.pathsep)
        real_paths = [p for p in current_path if "mock_bin" not in p]
        cls.openclaw_path = shutil.which("openclaw", path=os.pathsep.join(real_paths))

    def test_real_cli_discovery(self):
        """Test Case 1: Real CLI Discovery"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")
        
        result = subprocess.run([self.openclaw_path, "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("OpenClaw", result.stdout)

    def test_agents_list_shape_validation(self):
        """Test Case 2: Agents List Shape Validation"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        result = subprocess.run([self.openclaw_path, "agents", "list"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        
        # Validate output shape: should contain "Agents:" and cards like "- agent-id"
        self.assertIn("Agents:", result.stdout)
        
        lines = result.stdout.splitlines()
        # Find the line "Agents:"
        try:
            agents_header_index = next(i for i, line in enumerate(lines) if line.strip() == "Agents:")
        except StopIteration:
            self.fail("Could not find 'Agents:' header in output")
            
        # Check if there's at least one agent listed and it follows the card format
        agent_lines = lines[agents_header_index+1:]
        found_agent_card = False
        found_model_metadata = False
        
        for line in agent_lines:
            stripped = line.strip()
            if stripped.startswith("- "):
                found_agent_card = True
            if "Model:" in stripped:
                found_model_metadata = True
        
        # We expect at least one agent in this environment (e.g. 'main')
        self.assertTrue(found_agent_card, "Expected at least one agent card starting with '- '")
        self.assertTrue(found_model_metadata, "Expected 'Model:' metadata in agent cards")

    def test_unsupported_command_guard(self):
        """Test Case 3: Unsupported Command Guard"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        # Confirm `agents show` fails as expected
        # Current CLI says: error: too many arguments for 'agents'. Expected 0 arguments but got 2.
        result = subprocess.run([self.openclaw_path, "agents", "show", "main"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error", (result.stdout + result.stderr).lower())

    def test_command_surface_inventory(self):
        """Test Case 4: Command Surface Inventory"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        # message send
        result = subprocess.run([self.openclaw_path, "message", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("send", result.stdout.lower())

        # gateway restart
        result = subprocess.run([self.openclaw_path, "gateway", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("restart", result.stdout.lower())

    def test_agent_invocation_shape(self):
        """Test Case 5: Agent Invocation Shape"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        result = subprocess.run([self.openclaw_path, "agent", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--agent", result.stdout)
        self.assertIn("--message", result.stdout)
        self.assertIn("--session-id", result.stdout)

if __name__ == "__main__":
    unittest.main()
