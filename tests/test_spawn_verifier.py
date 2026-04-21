import unittest
from unittest.mock import patch, MagicMock
import os
import sys

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

        test_args = ["spawn_verifier.py", "--prd-files", "PRD1.md,PRD2.md", "--workdir", "/tmp/work"]
        
        with patch.object(sys, 'argv', test_args):
            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
                spawn_verifier.main()
            
        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for verifier")
        args, kwargs = mock_invoke_agent.call_args
        self.assertEqual(kwargs.get("role"), "verifier")
        mock_setup_key.assert_called()

if __name__ == '__main__':
    unittest.main()
