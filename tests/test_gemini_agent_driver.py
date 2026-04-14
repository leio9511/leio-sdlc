import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from agent_driver import invoke_agent

class TestGeminiAgentDriver(unittest.TestCase):
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_gemini_driver_constructs_correct_cmd(self, mock_resolve_cmd, mock_run):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="success")
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["SDLC_MODEL"] = "google/gemini-2.0-flash"
        
        with patch.dict(os.environ, env):
            invoke_agent("test task", session_key="test-session")
            
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        
        self.assertIn("--yolo", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[0], "/mock/bin/gemini")
        
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "google/gemini-2.0-flash")

    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_gemini_driver_env_var_priority(self, mock_resolve_cmd, mock_run):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="success")
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["TEST_MODEL"] = "fallback-model"
        env["SDLC_MODEL"] = "priority-model"
        
        with patch.dict(os.environ, env):
            invoke_agent("test task", session_key="test-session")
            
        cmd = mock_run.call_args[0][0]
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "priority-model")

if __name__ == "__main__":
    unittest.main()
