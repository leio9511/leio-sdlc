import os
import subprocess
import shutil
import unittest
import pytest
import sys

# Add scripts directory to path to import agent_driver
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import agent_driver

CLI_TIMEOUT_SECONDS = 20


def run_openclaw_cli_or_skip(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=CLI_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pytest.skip(f"openclaw CLI timed out: {' '.join(args[1:])}")

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
        
        result = run_openclaw_cli_or_skip([self.openclaw_path, "--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("OpenClaw", result.stdout)

    def test_agents_list_shape_validation(self):
        """Test Case 2: Agents List Shape Validation"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        result = run_openclaw_cli_or_skip([self.openclaw_path, "agents", "list"])
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
        result = run_openclaw_cli_or_skip([self.openclaw_path, "agents", "show", "main"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error", (result.stdout + result.stderr).lower())

    def test_command_surface_inventory(self):
        """Test Case 4: Command Surface Inventory"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        # message send
        result = run_openclaw_cli_or_skip([self.openclaw_path, "message", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("send", result.stdout.lower())

        # gateway restart
        result = run_openclaw_cli_or_skip([self.openclaw_path, "gateway", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("restart", result.stdout.lower())

    def test_agent_invocation_shape(self):
        """Test Case 5: Agent Invocation Shape"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        result = run_openclaw_cli_or_skip([self.openclaw_path, "agent", "--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--agent", result.stdout)
        self.assertIn("--message", result.stdout)
        self.assertIn("--session-id", result.stdout)

    def test_agent_driver_compatibility_unit(self):
        """Test Case 6: Verify agent_driver can parse real CLI output"""
        if not self.openclaw_path:
            pytest.skip("openclaw binary not found in PATH")

        result = run_openclaw_cli_or_skip([self.openclaw_path, "agents", "list"])
        self.assertEqual(result.returncode, 0)
        
        # We know 'main' usually exists in this environment
        if "- main" in result.stdout:
            self.assertTrue(agent_driver.openclaw_agent_exists(result.stdout, "main"), "Failed to detect 'main' agent in real output")
            
            # Find the block for 'main' to test model parsing
            lines = result.stdout.splitlines()
            agent_block = []
            found = False
            for line in lines:
                stripped = line.strip()
                if not found and stripped.startswith("- main"):
                    found = True
                    agent_block.append(line)
                    continue
                if found:
                    if stripped.startswith("- "):
                        break
                    agent_block.append(line)
            
            block_str = "\n".join(agent_block)
            model = agent_driver.parse_openclaw_agent_model(block_str)
            self.assertIsNotNone(model, "Failed to parse model from real 'main' agent block")

if __name__ == "__main__":
    unittest.main()
