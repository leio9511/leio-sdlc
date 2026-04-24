import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import agent_driver


class TestOpenClawModelAwareRouting(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "LLM_DRIVER": "openclaw",
                "HOME_MOCK": "/tmp/mock_home",
            },
            clear=False,
        )
        self.env.start()
        self.run = patch("agent_driver.subprocess.run")
        self.mock_run = self.run.start()
        self.resolve = patch("agent_driver.resolve_cmd", return_value="mock_openclaw")
        self.resolve.start()
        self.copytree = patch("shutil.copytree")
        self.mock_copytree = self.copytree.start()
        self.copy2 = patch("shutil.copy2")
        self.mock_copy2 = self.copy2.start()

    def tearDown(self):
        patch.stopall()

    def test_openclaw_agent_id_is_model_aware_for_alias_model(self):
        self.assertEqual(agent_driver.get_openclaw_agent_id("gpt"), "sdlc-generic-openclaw-gpt")

        list_res = MagicMock(stdout="sdlc-generic-openclaw-gpt\n", returncode=0)
        show_res = MagicMock(stdout="Model: gpt\n", returncode=0)
        run_res = MagicMock(stdout="ok", returncode=0)
        self.mock_run.side_effect = [list_res, show_res, run_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}, clear=False):
            agent_driver.invoke_agent("task", session_key="session-123")

        self.assertEqual(self.mock_run.call_args_list[1][0][0], ["mock_openclaw", "agents", "show", "sdlc-generic-openclaw-gpt"])
        cmd = self.mock_run.call_args_list[2][0][0]
        self.assertEqual(cmd[:7], ["mock_openclaw", "agent", "--agent", "sdlc-generic-openclaw-gpt", "--session-id", "session-123", "-m"])

    def test_openclaw_agent_id_is_model_aware_for_full_model_name(self):
        self.assertEqual(
            agent_driver.get_openclaw_agent_id("gemini-3.1-pro-preview"),
            "sdlc-generic-openclaw-gemini-3-1-pro-preview",
        )

    def test_openclaw_lazy_create_uses_requested_model_and_model_specific_agent(self):
        list_res = MagicMock(stdout="other-agent\n", returncode=0)
        create_res = MagicMock(stdout="created", returncode=0)
        run_res = MagicMock(stdout="ok", returncode=0)
        self.mock_run.side_effect = [list_res, create_res, run_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gemini-3.1-pro-preview"}, clear=False):
            with patch("os.listdir", return_value=["AGENTS.md"]):
                with patch("os.path.exists", side_effect=lambda p: True):
                    with patch("os.path.isdir", return_value=False):
                        with patch("os.makedirs"):
                            agent_driver.invoke_agent("task", session_key="session-123")

        create_cmd = self.mock_run.call_args_list[1][0][0]
        self.assertEqual(
            create_cmd[:5],
            ["mock_openclaw", "agents", "add", "sdlc-generic-openclaw-gemini-3-1-pro-preview", "--non-interactive"],
        )
        self.assertIn("--model", create_cmd)
        self.assertIn("gemini-3.1-pro-preview", create_cmd)

        run_cmd = self.mock_run.call_args_list[2][0][0]
        self.assertEqual(run_cmd[3], "sdlc-generic-openclaw-gemini-3-1-pro-preview")
        self.assertTrue(self.mock_copy2.called or self.mock_copytree.called)

    def test_openclaw_existing_matching_agent_is_reused_without_recreate(self):
        list_res = MagicMock(stdout="sdlc-generic-openclaw-gpt\n", returncode=0)
        show_res = MagicMock(stdout="Model: gpt\n", returncode=0)
        run_res = MagicMock(stdout="ok", returncode=0)
        self.mock_run.side_effect = [list_res, show_res, run_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}, clear=False):
            agent_driver.invoke_agent("task", session_key="session-123")

        self.assertEqual(len(self.mock_run.call_args_list), 3)
        self.assertEqual(self.mock_run.call_args_list[1][0][0], ["mock_openclaw", "agents", "show", "sdlc-generic-openclaw-gpt"])
        run_cmd = self.mock_run.call_args_list[2][0][0]
        self.assertEqual(run_cmd[3], "sdlc-generic-openclaw-gpt")


if __name__ == "__main__":
    unittest.main()
