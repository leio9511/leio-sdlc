import unittest
import os
import sys
import json
import io
from unittest.mock import patch, MagicMock

# Ensure we can import scripts
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from agent_driver import invoke_agent

class TestAgentDriverWorkdir(unittest.TestCase):
    @patch('agent_driver._resolve_engine_spec')
    @patch('agent_driver.subprocess.Popen')
    def test_missing_workdir_fails(self, mock_popen, mock_resolve_engine):
        mock_resolve_engine.return_value = {
            "runtime_mode": "direct_cli",
            "execution": {
                "executable": "agy",
                "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"}
            }
        }
        
        # We expect a SystemExit because we didn't pass workdir, and the engine has a workspace_arg
        # It should print a specific FATAL string to stderr
        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as e:
                invoke_agent("dummy task", session_key="123")
            
            self.assertEqual(e.exception.code, 1)
            self.assertIn("[FATAL] direct_cli engine with workspace_arg requires explicit workdir", mock_stderr.getvalue())

    @patch('agent_driver._resolve_engine_spec')
    @patch('agent_driver.subprocess.Popen')
    def test_provided_workdir_succeeds(self, mock_popen, mock_resolve_engine):
        mock_resolve_engine.return_value = {
            "runtime_mode": "direct_cli",
            "execution": {
                "executable": "agy",
                "workspace_arg": {"flag": "--add-dir", "value": "{workdir}"}
            }
        }
        
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_process.communicate.return_value = (b"mock stdout", b"mock stderr")
        mock_popen.return_value = mock_process
        
        # When workdir is explicitly provided, it should not sys.exit(1)
        try:
            res = invoke_agent("dummy task", session_key="123", workdir="/my/explicit/workdir")
        except SystemExit:
            self.fail("invoke_agent raised SystemExit unexpectedly!")
            
        # We also assert that the final resolved command contains the explicit workdir
        call_args = mock_popen.call_args[0][0] # cmd list
        self.assertIn("--add-dir", call_args)
        self.assertIn("/my/explicit/workdir", call_args)

    @patch('agent_driver._resolve_engine_spec')
    @patch('agent_driver.subprocess.Popen')
    def test_gemini_no_workspace_arg_succeeds(self, mock_popen, mock_resolve_engine):
        mock_resolve_engine.return_value = {
            "runtime_mode": "direct_cli",
            "execution": {
                "executable": "gemini",
                "workspace_arg": None
            }
        }
        
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        mock_process.communicate.return_value = (b"mock stdout", b"mock stderr")
        mock_popen.return_value = mock_process
        
        # Even without explicit workdir, gemini (which lacks workspace_arg) should succeed
        try:
            res = invoke_agent("dummy task", session_key="123")
        except SystemExit:
            self.fail("invoke_agent raised SystemExit unexpectedly for engine with no workspace_arg!")

    def test_static_config_agy_direct_cli(self):
        config_path = os.path.join(os.path.dirname(current_dir), "config", "engines.default.json")
        with open(config_path, 'r') as f:
            data = json.load(f)
            
        agy_spec = data.get("engines", {}).get("agy_direct_cli")
        self.assertIsNotNone(agy_spec)
        execution = agy_spec.get("execution", {})
        self.assertIsNone(execution.get("model_arg"))
        self.assertIsNone(execution.get("default_model"))
        
if __name__ == '__main__':
    unittest.main()
