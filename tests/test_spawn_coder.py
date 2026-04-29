import os
import sys
import tempfile
import unittest
from unittest.mock import patch, mock_open

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import builtins

import spawn_coder
from agent_driver import AgentResult

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

    @patch('spawn_coder.get_current_branch', return_value='feature/test')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.os.path.exists')
    @patch('envelope_assembler.os.makedirs')
    @patch('spawn_coder.invoke_agent')
    @patch('spawn_coder.build_coder_startup_packet_and_prompt')
    def test_handle_feedback_routing_with_stored_key(self, mock_build, mock_invoke, mock_makedirs, mock_exists, mock_commit, mock_branch):
        mock_exists.return_value = True

        def mock_file_open(path, *args, **kwargs):
            if "feedback.txt" in str(path):
                return mock_open(read_data="Fix the bugs.")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open(read_data="sdlc_coder_PR_001")(path, *args, **kwargs)
            return mock_open(read_data="")(path, *args, **kwargs)

        with patch('builtins.open', side_effect=mock_file_open):
            mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
            is_existing, key = spawn_coder.handle_feedback_routing("/tmp/work", ".", "PR.md", "PRD.md", "playbook.md", "feedback.txt", "PR_001")

        self.assertTrue(is_existing)
        self.assertEqual(key, "sdlc_coder_PR_001")
        mock_invoke.assert_called_once()
        called_msg = mock_invoke.call_args[0][0]
        called_kwargs = mock_invoke.call_args[1]
        self.assertEqual(called_kwargs['session_key'], "sdlc_coder_PR_001")
        self.assertIn("# REVIEW REPORT JSON", called_msg)
        self.assertIn("Fix the bugs.", called_msg)
        self.assertIn(spawn_coder.REVISION_CONTINUATION_RULE, called_msg)
        self.assertNotIn("# REFERENCE INDEX", called_msg)

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_initial_mode_uses_envelope_prompt(self, mock_setup_key, mock_invoke, mock_check_output):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            pr_content = "UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED"
            prd_content = "UNIQUE PRD BODY SHOULD NOT BE INLINED"
            with open(pr_file, "w") as f:
                f.write(pr_content)
            with open(prd_file, "w") as f:
                f.write(prd_content)

            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()

            self.assertTrue(mock_invoke.called)
            task_string = mock_invoke.call_args[0][0]
            self.assertTrue(task_string.startswith("# EXECUTION CONTRACT"))
            self.assertIn(os.path.abspath(pr_file), task_string)
            self.assertIn(os.path.abspath(prd_file), task_string)
            self.assertIn(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks", "coder_playbook.md")), task_string)
            self.assertNotIn(pr_content, task_string)
            self.assertNotIn(prd_content, task_string)
            mock_setup_key.assert_called_once()

            packet_file = os.path.join(tmp_dir, "coder_debug", "initial", "startup_packet.json")
            prompt_file = os.path.join(tmp_dir, "coder_debug", "initial", "rendered_prompt.txt")
            self.assertTrue(os.path.exists(packet_file))
            self.assertTrue(os.path.exists(prompt_file))

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
            if "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open()(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--feedback-file", "feedback.json", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()

        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        self.assertIn(spawn_coder.RECOVERY_CONTINUATION_WARNING, prompt_sent)
        self.assertIn("# REVIEW REPORT JSON", prompt_sent)
        self.assertIn('{"status": "NEEDS_FIX", "comments": "Missing stuff"}', prompt_sent)
        self.assertIn(os.path.abspath("feedback.json"), prompt_sent)
        self.assertNotIn("# REFERENCE INDEX", prompt_sent)
        mock_setup_key.assert_called_once()

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_mocked_revision_flow_prompt_injection_existing_session(self, mock_setup_key, mock_exists, mock_invoke, mock_check_output):
        def custom_exists(path):
            if ".coder_session" in str(path):
                return True
            if "PR" in str(path) or "PRD" in str(path) or "feedback" in str(path) or "prompts.json" in str(path):
                return True
            return real_exists(path)

        mock_exists.side_effect = custom_exists

        def mock_file_open(path, *args, **kwargs):
            if "feedback" in str(path):
                return mock_open(read_data='{"status": "NEEDS_FIX", "comments": "Missing stuff"}')(path, *args, **kwargs)
            if "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open(read_data="sdlc_coder_PR_001_1234abcd")(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--feedback-file", "feedback.json", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false", "SDLC_FORCE_NEW_CODER_SESSION": "0"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001_1234abcd", stdout="")

                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()

        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        called_kwargs = mock_invoke.call_args[1]
        self.assertEqual(called_kwargs['session_key'], "sdlc_coder_PR_001_1234abcd")
        self.assertIn("# REVIEW REPORT JSON", prompt_sent)
        self.assertIn('{"status": "NEEDS_FIX", "comments": "Missing stuff"}', prompt_sent)
        self.assertIn(spawn_coder.REVISION_CONTINUATION_RULE, prompt_sent)
        self.assertIn("not a fresh task", prompt_sent.lower())
        self.assertNotIn("# REFERENCE INDEX", prompt_sent)
        mock_setup_key.assert_called_once()

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
            if ".coder_session" in str(path):
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
        self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt_sent)
        self.assertIn("git dirty", prompt_sent)
        self.assertNotIn("System alert requiring corrective action:", prompt_sent)
        self.assertIn(spawn_coder.RECOVERY_CONTINUATION_WARNING, prompt_sent)
        mock_setup_key.assert_called_once()


if __name__ == '__main__':
    unittest.main()
