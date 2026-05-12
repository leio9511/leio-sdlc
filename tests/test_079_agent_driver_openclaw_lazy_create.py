import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add scripts directory to path to import agent_driver
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import agent_driver

class TestAgentDriverOpenclawLazyCreate(unittest.TestCase):
    def setUp(self):
        self.patcher_env = patch.dict(os.environ, {"LLM_DRIVER": "openclaw", "HOME_MOCK": "/tmp/mock_home"})
        self.patcher_env.start()
        self.patcher_run = patch('agent_driver.subprocess.run')
        self.mock_run = self.patcher_run.start()
        self.patcher_popen = patch('agent_driver.subprocess.Popen')
        self.mock_popen = self.patcher_popen.start()
        # Ensure we don't accidentally do actual shell things
        self.patcher_resolve = patch('agent_driver.resolve_cmd')
        self.mock_resolve = self.patcher_resolve.start()
        self.mock_resolve.return_value = "mock_openclaw"

        # We need to mock some file operations if they happen
        self.patcher_copytree = patch('shutil.copytree')
        self.mock_copytree = self.patcher_copytree.start()
        self.patcher_copy2 = patch('shutil.copy2')
        self.mock_copy2 = self.patcher_copy2.start()

    def tearDown(self):
        patch.stopall()

    def _setup_popen(self, stdout_text="output", stderr_text="", return_code=0):
        def side_effect(cmd, stdout=None, stderr=None, start_new_session=None, env=None, **kwargs):
            if stdout is not None:
                stdout.write(stdout_text)
                stdout.flush()
            if stderr is not None:
                stderr.write(stderr_text)
                stderr.flush()
            proc = MagicMock()
            proc.wait.return_value = return_code
            return proc

        self.mock_popen.side_effect = side_effect

    def test_openclaw_adapter_resolves_model_specific_agent(self):
        # Setup: agent exists
        mock_result_list = MagicMock()
        mock_result_list.stdout = "- sdlc-generic-openclaw-gpt\n  Model: gpt\n- other-agent\n  Model: claudette\n"
        mock_result_list.returncode = 0

        # Now validate_openclaw_agent_model also calls agents list
        self.mock_run.side_effect = [mock_result_list, mock_result_list]
        self._setup_popen(stdout_text="output")

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-123")

        calls = self.mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["mock_openclaw", "agents", "list"])
        # Second call is from validate_openclaw_agent_model
        self.assertEqual(calls[1][0][0], ["mock_openclaw", "agents", "list"])
        cmd = self.mock_popen.call_args_list[0][0][0]
        # Semantic thinking-aware assertions
        self.assertIn("--thinking", cmd)
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "high")
        self.assertIn("--agent", cmd)
        self.assertIn("sdlc-generic-openclaw-gpt", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-123", cmd)
        self.assertIn("-m", cmd)
        m_idx = cmd.index("-m")
        self.assertTrue(cmd[m_idx + 1].startswith("Read your complete task instructions"))

    def test_openclaw_multi_line_parsing_unit(self):
        sample_output = """
- sdlc-generic-openclaw-gpt
  Workspace: /root/.openclaw/agents/sdlc-generic-openclaw-gpt/workspace
  Agent dir: /root/.openclaw/agents/sdlc-generic-openclaw-gpt/agent
  Model: gpt
  Routing rules: 0
- other-agent
  Model: claudette
"""
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "sdlc-generic-openclaw-gpt"))
        self.assertTrue(agent_driver.openclaw_agent_exists(sample_output, "other-agent"))
        self.assertFalse(agent_driver.openclaw_agent_exists(sample_output, "non-existent"))

        # Test model extraction
        self.assertEqual(agent_driver.parse_openclaw_agent_model(sample_output), "gpt")

        block_gpt = "- sdlc-generic-openclaw-gpt\n  Model: gpt"
        self.assertEqual(agent_driver.parse_openclaw_agent_model(block_gpt), "gpt")

        block_other = "- other-agent\n  Model: claudette"
        self.assertEqual(agent_driver.parse_openclaw_agent_model(block_other), "claudette")

    def test_lazy_creation_logic_invoked_with_model_specific_agent(self):
        # Setup: agent missing
        mock_result_list = MagicMock()
        mock_result_list.stdout = "other-agent\n"
        mock_result_list.returncode = 0

        mock_result_create = MagicMock()
        mock_result_create.returncode = 0

        self.mock_run.side_effect = [mock_result_list, mock_result_create]
        self._setup_popen(stdout_text="output")

        # Mock os.listdir to trigger file copy
        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}):
            with patch('os.listdir', return_value=['AGENTS.md']):
                with patch('os.path.exists', return_value=True):
                    with patch('os.path.isdir', return_value=False):
                        with patch('os.makedirs'):
                            agent_driver.invoke_agent("test task", session_key="session-123")

        calls = self.mock_run.call_args_list

        # Check create command
        create_cmd = calls[1][0][0]
        self.assertEqual(create_cmd[:5], ["mock_openclaw", "agents", "add", "sdlc-generic-openclaw-gpt", "--non-interactive"])
        self.assertIn("--model", create_cmd)

        # Check copy was called
        self.assertTrue(self.mock_copy2.called or self.mock_copytree.called)

        # Semantic thinking-aware assertions on run command
        run_cmd = self.mock_popen.call_args_list[0][0][0]
        self.assertIn("--thinking", run_cmd)
        think_idx = run_cmd.index("--thinking")
        self.assertEqual(run_cmd[think_idx + 1], "high")

    def test_gemini_path_unchanged(self):
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            self.mock_resolve.return_value = "mock_gemini"

            mock_result_list = MagicMock()
            mock_result_list.stdout = "[]"
            mock_result_list.returncode = 0

            self.mock_run.side_effect = [mock_result_list]
            self._setup_popen(stdout_text="output")

            agent_driver.invoke_agent("test task", session_key="session-123")

            cmd = self.mock_popen.call_args_list[0][0][0]
            self.assertEqual(cmd[:3], ["mock_gemini", "--yolo", "-p"])
            self.assertNotIn("--agent", cmd)
            self.assertNotIn("sdlc-generic-openclaw", cmd)
            self.assertNotIn("--thinking", cmd)

    def test_openclaw_agent_exists_with_annotations_integration(self):
        # Setup: agent exists with annotation
        mock_result_list = MagicMock()
        mock_result_list.stdout = "- sdlc-generic-openclaw-gpt (default)\n  Model: gpt\n"
        mock_result_list.returncode = 0

        # We call agents list twice: once in openclaw_agent_exists, once in validate_openclaw_agent_model
        self.mock_run.side_effect = [mock_result_list, mock_result_list]
        self._setup_popen(stdout_text="output")

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-123")

        # If it didn't crash and called the agent, it means it correctly detected it.
        calls = self.mock_run.call_args_list
        self.assertEqual(calls[0][0][0], ["mock_openclaw", "agents", "list"])
        cmd = self.mock_popen.call_args_list[0][0][0]
        # Semantic thinking-aware assertions
        self.assertIn("--thinking", cmd)
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "high")
        self.assertIn("--agent", cmd)
        self.assertIn("sdlc-generic-openclaw-gpt", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-123", cmd)
        self.assertIn("-m", cmd)
        m_idx = cmd.index("-m")
        self.assertTrue(cmd[m_idx + 1].startswith("Read your complete task instructions"))

    def test_explicit_thinking_passed_through(self):
        # Call invoke_agent with explicit thinking="xhigh"
        mock_result_list = MagicMock()
        mock_result_list.stdout = "- sdlc-generic-openclaw-gpt\n  Model: gpt\n"
        mock_result_list.returncode = 0

        self.mock_run.side_effect = [mock_result_list, mock_result_list]
        self._setup_popen(stdout_text="output")

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-123", thinking="xhigh")

        cmd = self.mock_popen.call_args_list[0][0][0]
        self.assertIn("--thinking", cmd)
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "xhigh")
        self.assertIn("--agent", cmd)
        self.assertIn("sdlc-generic-openclaw-gpt", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-123", cmd)
        self.assertIn("-m", cmd)
        m_idx = cmd.index("-m")
        self.assertTrue(cmd[m_idx + 1].startswith("Read your complete task instructions"))

    def test_default_thinking_is_high(self):
        # Call invoke_agent without explicit thinking and verify default "high"
        mock_result_list = MagicMock()
        mock_result_list.stdout = "- sdlc-generic-openclaw-gpt\n  Model: gpt\n"
        mock_result_list.returncode = 0

        self.mock_run.side_effect = [mock_result_list, mock_result_list]
        self._setup_popen(stdout_text="output")

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-123")

        cmd = self.mock_popen.call_args_list[0][0][0]
        self.assertIn("--thinking", cmd)
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "high")
        self.assertIn("--agent", cmd)
        self.assertIn("sdlc-generic-openclaw-gpt", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-123", cmd)
        self.assertIn("-m", cmd)
        m_idx = cmd.index("-m")
        self.assertTrue(cmd[m_idx + 1].startswith("Read your complete task instructions"))

if __name__ == '__main__':
    unittest.main()
