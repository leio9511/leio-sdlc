import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import spawn_coder

class TestSpawnCoder(unittest.TestCase):
    def test_extract_pr_id(self):
        self.assertEqual(spawn_coder.extract_pr_id("docs/PR_001_Test.md"), "PR_001")
        self.assertEqual(spawn_coder.extract_pr_id("PR_123_Something.md"), "PR_123")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_Fix.md"), "PR_003_1")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_2_Something.md"), "PR_003_1_2")
        self.assertEqual(spawn_coder.extract_pr_id("NoPrefix.md"), "NoPrefix")

    @patch('spawn_coder.subprocess.run')
    def test_openclaw_agent_call(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ''
        mock_run.return_value = mock_result

        key = spawn_coder.openclaw_agent_call("sdlc_coder_PR_001", "test task")

        self.assertEqual(key, "sdlc_coder_PR_001")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[:6], ["openclaw", "agent", "--local", "--session-id", "sdlc_coder_PR_001", "--message"])
        self.assertEqual(cmd[6], "test task")
        for arg in cmd:
            self.assertNotIn("sessions_spawn", arg)
            self.assertNotIn("sessions_send", arg)

    @patch('spawn_coder.openclaw_agent_call')
    def test_send_feedback(self, mock_call):
        spawn_coder.send_feedback("sdlc_coder_PR_001", "feedback message")
        mock_call.assert_called_once_with("sdlc_coder_PR_001", "feedback message", workdir='.')

    @patch('spawn_coder.os.path.exists')
    @patch('spawn_coder.openclaw_agent_call')
    @patch('spawn_coder.build_prompt')
    def test_handle_feedback_routing_with_stored_key(self, mock_build, mock_call, mock_exists):
        mock_build.return_value = "Mocked feedback prompt"

        m_open = mock_open(read_data="Fix the bugs.")
        with patch('builtins.open', m_open):
            mock_exists.return_value = True
            is_existing, key = spawn_coder.handle_feedback_routing("/tmp/work", "feedback.txt", "task string", "PR_001")

            self.assertTrue(is_existing)
            self.assertEqual(key, "sdlc_coder_PR_001")
            mock_call.assert_called_once()
            called_key, called_msg = mock_call.call_args[0]
            self.assertEqual(called_key, "sdlc_coder_PR_001")
            self.assertIn("Mocked feedback prompt", called_msg)

    @patch('spawn_coder.subprocess.run')
    @patch('spawn_coder.openclaw_agent_call')
    @patch('os.path.exists')
    @patch('spawn_coder.build_prompt')
    def test_playbook_injection(self, mock_build, mock_exists, mock_agent_call, mock_run):
        mock_build.return_value = "--- CODER PLAYBOOK ---\nplaybook content\nstrictly forbidden from manually editing the markdown file's `status` field"
    
        # Mocking for the main block
        mock_exists.side_effect = lambda p: True if "playbook" in p or "PR" in p or "PRD" in p else False
    
        # We need to simulate the sys.argv and call main()
        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--workdir", "/tmp"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                # Also mock git branch check
                mock_run.return_value.stdout = "feature/test"
                mock_run.return_value.returncode = 0
        
                m_open = mock_open(read_data="playbook content")
                with patch('builtins.open', m_open):
                    spawn_coder.main()

            # Verify openclaw_agent_call was called with task_string containing playbook
            self.assertTrue(mock_agent_call.called)
            task_string = mock_agent_call.call_args[0][1]
            self.assertIn("--- CODER PLAYBOOK ---", task_string)
            self.assertIn("playbook content", task_string)
            self.assertIn("strictly forbidden from manually editing the markdown file's `status` field", task_string)

if __name__ == '__main__':
    unittest.main()
