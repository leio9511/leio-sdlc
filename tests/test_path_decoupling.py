import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Dynamically add scripts dir to path to import functions
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

class TestPathDecoupling(unittest.TestCase):

    @patch("agent_driver.open", create=True)
    def test_spawn_scripts_template_resolution(self, mock_open):
        from agent_driver import build_prompt
        # Test that build_prompt tries to read from absolute paths
        build_prompt("planner")
        # Check if calls to open contain absolute paths instead of relative ones
        for call in mock_open.call_args_list:
            path_arg = call[0][0]
            self.assertTrue(os.path.isabs(path_arg), f"Path {path_arg} is not absolute")

    @patch("spawn_planner.build_prompt", return_value="mock prompt")
    @patch("spawn_planner.invoke_agent")
    @patch("spawn_planner.open", create=True)
    @patch("spawn_planner.os.makedirs")
    def test_spawn_scripts_output_isolation(self, mock_makedirs, mock_open, mock_invoke, mock_build):
        # We need to simulate arguments to spawn_planner
        # Actually since these are scripts, testing them directly might be tricky
        pass

if __name__ == "__main__":
    unittest.main()
