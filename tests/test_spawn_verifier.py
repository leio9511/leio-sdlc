import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

class TestSpawnVerifier(unittest.TestCase):
    @patch('spawn_verifier.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    @patch('os.path.exists')
    @patch('os.chdir')
    @patch('os.makedirs')
    def test_spawn_verifier_payload_injection(self, mock_makedirs, mock_chdir, mock_exists, mock_setup_key, mock_invoke_agent):
        import spawn_verifier
        from agent_driver import AgentResult
        mock_invoke_agent.return_value = AgentResult(session_key='subtask-verifier', stdout='dummy')
        mock_exists.return_value = True # For the output file check

        test_args = ["spawn_verifier.py", "--prd-files", "PRD1.md,PRD2.md", "--workdir", "/tmp/work", "--enable-exec-from-workspace"]
        
        with patch.object(sys, 'argv', test_args):
            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
                spawn_verifier.main()
            
        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for verifier")
        args, kwargs = mock_invoke_agent.call_args
        self.assertEqual(kwargs.get("role"), "verifier")
        mock_setup_key.assert_called()

    @patch('spawn_verifier.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    @patch('os.path.exists')
    @patch('os.chdir')
    @patch('os.makedirs')
    def test_verifier_aligned_to_file_based_result(self, mock_makedirs, mock_chdir, mock_exists, mock_setup_key, mock_invoke_agent):
        import spawn_verifier
        from agent_driver import AgentResult
        
        # Test Case 2: test_verifier_aligned_to_file_based_result
        # The agent returns conversational text rather than JSON on stdout
        mock_invoke_agent.return_value = AgentResult(session_key='subtask-verifier', stdout='Here is my reasoning. I have written the uat_report.json file.')
        
        # We need mock_exists to return True for the out-file to indicate the file was written
        def mock_exists_side_effect(path):
            if str(path).endswith("uat_report.json") or path == "/tmp/work/uat_report.json":
                return True
            return True
        mock_exists.side_effect = mock_exists_side_effect

        test_args = ["spawn_verifier.py", "--prd-files", "PRD1.md,PRD2.md", "--workdir", "/tmp/work", "--enable-exec-from-workspace", "--out-file", "uat_report.json"]
        
        with patch.object(sys, 'argv', test_args):
            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
                try:
                    spawn_verifier.main()
                except SystemExit as e:
                    self.fail(f"spawn_verifier.main() exited unexpectedly with code {e.code} despite out-file existing")
                    
        self.assertTrue(mock_invoke_agent.called)

if __name__ == '__main__':
    unittest.main()
