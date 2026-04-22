import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import spawn_coder
from agent_driver import AgentResult
import builtins

real_open = builtins.open
real_exists = os.path.exists

class TestSpawnCoder(unittest.TestCase):
    def test_extract_pr_id(self):
        self.assertEqual(spawn_coder.extract_pr_id("docs/PR_001_Test.md"), "PR_001")
        self.assertEqual(spawn_coder.extract_pr_id("PR_123_Something.md"), "PR_123")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_Fix.md"), "PR_003_1")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_2_Something.md"), "PR_003_1_2")
        self.assertEqual(spawn_coder.extract_pr_id("NoPrefix.md"), "NoPrefix")

    @patch('spawn_coder.invoke_agent')
    def test_send_feedback(self, mock_call):
        mock_call.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        spawn_coder.send_feedback("sdlc_coder_PR_001", "feedback message")
        mock_call.assert_called_once_with("feedback message", session_key="sdlc_coder_PR_001", role="coder", run_dir=".")

    @patch('spawn_coder.os.path.exists')
    @patch('spawn_coder.invoke_agent')
    @patch('spawn_coder.build_prompt')
    def test_handle_feedback_routing_with_stored_key(self, mock_build, mock_invoke, mock_exists):
        mock_build.return_value = "Mocked feedback prompt"
        mock_exists.return_value = True

        def mock_file_open(path, *args, **kwargs):
            if "feedback.txt" in str(path):
                return mock_open(read_data="Fix the bugs.")(path, *args, **kwargs)
            elif ".coder_session" in str(path):
                return mock_open(read_data="sdlc_coder_PR_001")(path, *args, **kwargs)
            else:
                return mock_open(read_data="")(path, *args, **kwargs)

        with patch('builtins.open', side_effect=mock_file_open):
            with patch.dict(os.environ, {"SDLC_FORCE_NEW_CODER_SESSION": "0"}):
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
                is_existing, key = spawn_coder.handle_feedback_routing("/tmp/work", "feedback.txt", "task string", "PR_001")

            self.assertTrue(is_existing)
            self.assertEqual(key, "sdlc_coder_PR_001")
            mock_invoke.assert_called_once()
            called_msg = mock_invoke.call_args[0][0]
            called_kwargs = mock_invoke.call_args[1]
            self.assertEqual(called_kwargs['session_key'], "sdlc_coder_PR_001")
            self.assertEqual(called_msg, "Mocked feedback prompt")

    @patch('spawn_coder.subprocess.run')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('spawn_coder.build_prompt')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_playbook_injection(self, mock_setup_key, mock_build, mock_exists, mock_invoke, mock_run):
        mock_build.return_value = "--- CODER PLAYBOOK ---\nplaybook content\nstrictly forbidden from manually editing the markdown file's `status` field"
    
        # Mocking for the main block
        mock_exists.side_effect = lambda p: True if "playbook" in str(p) or "PR" in str(p) or "PRD" in str(p) else False
    
        # We need to simulate the sys.argv and call main()
        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                # Also mock git branch check
                mock_run.return_value = MagicMock()
                mock_run.return_value.stdout = "feature/test"
                mock_run.return_value.returncode = 0
                
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        
                m_open = mock_open(read_data="playbook content")
                with patch('builtins.open', m_open):
                    spawn_coder.main()

            # Verify invoke_agent was called with task_string containing playbook
            self.assertTrue(mock_invoke.called)
            task_string = mock_invoke.call_args[0][0]
            self.assertIn("--- CODER PLAYBOOK ---", task_string)
            self.assertIn("playbook content", task_string)
            self.assertIn("strictly forbidden from manually editing the markdown file's `status` field", task_string)
            mock_setup_key.assert_called_once()

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_mocked_revision_flow_prompt_injection(self, mock_setup_key, mock_exists, mock_invoke, mock_check_output):
        def custom_exists(path):
            if ".coder_session" in str(path):
                return False
            if "PR" in str(path) or "PRD" in str(path) or "feedback" in str(path) or "prompts.json" in str(path):
                return True
            return real_exists(path)
        mock_exists.side_effect = custom_exists

        def mock_file_open(path, *args, **kwargs):
            if "feedback" in str(path):
                return mock_open(read_data='{"status": "NEEDS_FIX", "comments": "Missing stuff"}')(path, *args, **kwargs)
            elif "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            elif ".coder_session" in str(path):
                return mock_open()(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--feedback-file", "feedback.json", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        
                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()
                    
        # Check that invoke_agent was called with the hardened prompt
        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        
        # Verify the hardened revision text is in the prompt
        self.assertIn("This is an execution task, not an acknowledgment task", prompt_sent)
        self.assertIn("You MUST NOT respond with only an acknowledgment such as", prompt_sent)
        self.assertIn("If you do not make code changes after revision feedback, you have failed the task", prompt_sent)
        self.assertIn("Commit the required files explicitly", prompt_sent)

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_mocked_system_alert_prompt_injection(self, mock_setup_key, mock_exists, mock_invoke, mock_check_output):
        def custom_exists(path):
            if ".coder_session" in str(path):
                return False
            if "PR" in str(path) or "PRD" in str(path) or "prompts.json" in str(path):
                return True
            return real_exists(path)
        mock_exists.side_effect = custom_exists

        def mock_file_open(path, *args, **kwargs):
            if "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            elif ".coder_session" in str(path):
                return mock_open()(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--system-alert", "git dirty", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        
                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()
                    
        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        
        self.assertIn("System Preflight or Git Workspace Check Failed", prompt_sent)
        self.assertIn("git dirty", prompt_sent)
        self.assertIn("This alert requires corrective action, not acknowledgment only", prompt_sent)

if __name__ == '__main__':
    unittest.main()
