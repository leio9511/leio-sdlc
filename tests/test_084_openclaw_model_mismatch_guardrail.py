import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import agent_driver
from config import OPENCLAW_MODEL_MISMATCH_ERROR


class TestOpenClawModelMismatchGuardrail(unittest.TestCase):
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
        self.copytree.start()
        self.copy2 = patch("shutil.copy2")
        self.copy2.start()

    def tearDown(self):
        patch.stopall()

    def test_openclaw_existing_agent_with_matching_model_runs_normally(self):
        list_res = MagicMock(stdout="sdlc-generic-openclaw-gpt\n", returncode=0)
        show_res = MagicMock(stdout="Model: gpt\n", returncode=0)
        run_res = MagicMock(stdout="ok", returncode=0)
        self.mock_run.side_effect = [list_res, show_res, run_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}, clear=False):
            result = agent_driver.invoke_agent("task", session_key="session-123")

        self.assertEqual(result.stdout, "ok")
        self.assertEqual(self.mock_run.call_args_list[1][0][0], ["mock_openclaw", "agents", "show", "sdlc-generic-openclaw-gpt"])
        self.assertEqual(self.mock_run.call_args_list[2][0][0][3], "sdlc-generic-openclaw-gpt")

    def test_openclaw_mismatch_fails_fast_with_exact_error_string(self):
        list_res = MagicMock(stdout="sdlc-generic-openclaw-gpt\n", returncode=0)
        show_res = MagicMock(stdout="Model: gemini-3.1-pro-preview\n", returncode=0)
        self.mock_run.side_effect = [list_res, show_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}, clear=False):
            with patch("sys.stderr", new_callable=lambda: __import__("io").StringIO()) as fake_stderr:
                with self.assertRaises(SystemExit) as ctx:
                    agent_driver.invoke_agent("task", session_key="session-123")

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(
            fake_stderr.getvalue().strip(),
            OPENCLAW_MODEL_MISMATCH_ERROR.format(
                requested_model="gpt",
                agent_id="sdlc-generic-openclaw-gpt",
                actual_model="gemini-3.1-pro-preview",
            ),
        )
        self.assertEqual(len(self.mock_run.call_args_list), 2)

    def test_openclaw_new_agent_path_does_not_trigger_mismatch_guardrail(self):
        list_res = MagicMock(stdout="other-agent\n", returncode=0)
        create_res = MagicMock(stdout="created", returncode=0)
        run_res = MagicMock(stdout="ok", returncode=0)
        self.mock_run.side_effect = [list_res, create_res, run_res]

        with patch.dict(os.environ, {"SDLC_MODEL": "gpt"}, clear=False):
            with patch("os.listdir", return_value=["AGENTS.md"]):
                with patch("os.path.exists", return_value=True):
                    with patch("os.path.isdir", return_value=False):
                        with patch("os.makedirs"):
                            result = agent_driver.invoke_agent("task", session_key="session-123")

        self.assertEqual(result.stdout, "ok")
        invoked = [call[0][0] for call in self.mock_run.call_args_list]
        self.assertNotIn(["mock_openclaw", "agents", "show", "sdlc-generic-openclaw-gpt"], invoked)

    def test_non_openclaw_engines_skip_mismatch_guardrail(self):
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
            mock_result_run = MagicMock(stdout="output", returncode=0)
            mock_result_list = MagicMock(stdout="[]", returncode=0)
            self.mock_run.side_effect = [mock_result_run, mock_result_list]
            self.resolve.stop()
            with patch("agent_driver.resolve_cmd", return_value="mock_gemini"):
                agent_driver.invoke_agent("test task", session_key="session-123")

        calls = [call[0][0] for call in self.mock_run.call_args_list]
        self.assertFalse(any(cmd[:3] == ["mock_openclaw", "agents", "show"] for cmd in calls if isinstance(cmd, list)))


if __name__ == "__main__":
    unittest.main()
