import json
import os
import sys
import tempfile as stdlib_tempfile
import unittest
from unittest.mock import MagicMock, mock_open, patch

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
import config
from agent_driver import AgentResult, invoke_agent

REAL_MKSTEMP = stdlib_tempfile.mkstemp


def fake_popen_factory(stdout_text="", stderr_text="", return_code=0, calls=None):
    def _fake_popen(cmd, stdout=None, stderr=None, start_new_session=None, env=None, **kwargs):
        if calls is not None:
            calls.append(
                {
                    "cmd": cmd,
                    "start_new_session": start_new_session,
                    "env": env,
                    "stdout_name": getattr(stdout, "name", None),
                    "stderr_name": getattr(stderr, "name", None),
                }
            )
        if stdout is not None:
            stdout.write(stdout_text)
            stdout.flush()
        if stderr is not None:
            stderr.write(stderr_text)
            stderr.flush()
        proc = MagicMock()
        proc.wait.return_value = return_code
        return proc

    return _fake_popen


class TestGeminiAgentDriver(unittest.TestCase):
    def test_invoke_agent_returns_agentresult(self):
        popen_calls = []
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("test stdout", "test stderr", 0, popen_calls),
                    ):
                        result = invoke_agent("test task", session_key="test-session")

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
        self.assertEqual(result.stdout, "test stdout")
        self.assertEqual(result.stderr, "test stderr")
        self.assertEqual(result.return_code, 0)
        self.assertEqual(len(popen_calls), 1)
        self.assertTrue(popen_calls[0]["start_new_session"])

    def test_gemini_driver_constructs_correct_cmd(self):
        popen_calls = []
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["SDLC_MODEL"] = "google/gemini-2.0-flash"

        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                    ):
                        invoke_agent("test task", session_key="test-session")

        cmd = popen_calls[0]["cmd"]
        self.assertIn("--yolo", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[0], "/mock/bin/gemini")

        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "google/gemini-2.0-flash")

    def test_gemini_driver_env_var_priority(self):
        popen_calls = []
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["TEST_MODEL"] = "fallback-model"
        env["SDLC_MODEL"] = "priority-model"

        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                    ):
                        invoke_agent("test task", session_key="test-session")

        cmd = popen_calls[0]["cmd"]
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "priority-model")

    def test_config_externalization(self):
        popen_calls = []
        env = {"LLM_DRIVER": "gemini"}

        with patch.dict(os.environ, env, clear=True):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                    ):
                        invoke_agent("test task", session_key="test-session")

        cmd = popen_calls[0]["cmd"]
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], config.DEFAULT_GEMINI_MODEL)
        self.assertEqual(config.DEFAULT_GEMINI_MODEL, "gemini-3.1-pro-preview")

    def test_mock_short_circuit_returns_mock_payload_without_launching_subprocess(self):
        with patch.dict(
            os.environ,
            {
                "LLM_DRIVER": "gemini",
                "SDLC_MOCK_LLM_RESPONSE": "mock payload",
            },
            clear=False,
        ):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run") as mock_run:
                    with patch("agent_driver.subprocess.Popen") as mock_popen:
                        result = invoke_agent("test task", session_key="test-session")

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
        self.assertEqual(result.stdout, "mock payload")
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.return_code, 0)
        mock_run.assert_not_called()
        mock_popen.assert_not_called()

    def test_invoke_agent_with_run_dir(self):
        popen_calls = []
        mkstemp_calls = []

        def fake_mkstemp(*args, **kwargs):
            fd, path = REAL_MKSTEMP(*args, **kwargs)
            mkstemp_calls.append({"kwargs": dict(kwargs), "path": path})
            return fd, path

        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                    with patch("agent_driver.tempfile.mkstemp", side_effect=fake_mkstemp):
                        with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                            with patch(
                                "agent_driver.subprocess.Popen",
                                side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                            ):
                                result = invoke_agent("test task", session_key="test-session", run_dir=run_dir)

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
        self.assertGreaterEqual(len(mkstemp_calls), 3)
        self.assertEqual(mkstemp_calls[0]["kwargs"]["dir"], os.path.join(run_dir, ".tmp"))
        self.assertEqual(mkstemp_calls[0]["kwargs"]["prefix"], "sdlc_prompt_test-session_")

    def test_invoke_agent_fallback_tempdir(self):
        popen_calls = []
        mkstemp_calls = []

        def fake_mkstemp(*args, **kwargs):
            fd, path = REAL_MKSTEMP(*args, **kwargs)
            mkstemp_calls.append({"kwargs": dict(kwargs), "path": path})
            return fd, path

        with stdlib_tempfile.TemporaryDirectory() as fake_tmp:
            def fake_exists(path):
                return path == fake_tmp

            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                    with patch("agent_driver.tempfile.gettempdir", return_value=fake_tmp):
                        with patch("agent_driver.os.path.exists", side_effect=fake_exists):
                            with patch("agent_driver.tempfile.mkstemp", side_effect=fake_mkstemp):
                                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                                    with patch(
                                        "agent_driver.subprocess.Popen",
                                        side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                                    ):
                                        result = invoke_agent("test task", session_key="test-session", run_dir="/mock/nonexistent")

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
        self.assertGreaterEqual(len(mkstemp_calls), 3)
        self.assertEqual(mkstemp_calls[0]["kwargs"]["dir"], fake_tmp)
        self.assertEqual(mkstemp_calls[0]["kwargs"]["prefix"], "sdlc_prompt_test-session_")

    def test_file_indirection_prompt_format(self):
        popen_calls = []
        mkstemp_calls = []

        def fake_mkstemp(*args, **kwargs):
            fd, path = REAL_MKSTEMP(*args, **kwargs)
            mkstemp_calls.append(path)
            return fd, path

        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.tempfile.mkstemp", side_effect=fake_mkstemp):
                    with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                        with patch(
                            "agent_driver.subprocess.Popen",
                            side_effect=fake_popen_factory("test stdout", "", 0, popen_calls),
                        ):
                            invoke_agent("test task", session_key="test-session")

        prompt_path = mkstemp_calls[0]
        cmd = popen_calls[0]["cmd"]
        p_idx = cmd.index("-p")
        prompt_arg = cmd[p_idx + 1]
        self.assertEqual(prompt_arg, f"Read your complete task instructions from {prompt_path}. Do not modify this file.")

    def test_lock_free_session_resume(self):
        popen_calls = []

        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            temp_dir = os.path.join(run_dir, ".tmp")
            os.makedirs(temp_dir, exist_ok=True)
            session_map_file = os.path.join(temp_dir, ".session_map_test-session.json")
            with open(session_map_file, "w", encoding="utf-8") as handle:
                json.dump({"actual_id": "RESUMED_UUID_456"}, handle)

            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                    with patch("agent_driver.subprocess.run") as mock_run:
                        with patch(
                            "agent_driver.subprocess.Popen",
                            side_effect=fake_popen_factory("success", "", 0, popen_calls),
                        ):
                            invoke_agent("test task", session_key="test-session", run_dir=run_dir)

        cmd = popen_calls[0]["cmd"]
        self.assertIn("-r", cmd)
        r_idx = cmd.index("-r")
        self.assertEqual(cmd[r_idx + 1], "RESUMED_UUID_456")
        mock_run.assert_not_called()

    def test_session_uuid_capture(self):
        popen_calls = []
        mkstemp_calls = []

        def fake_mkstemp(*args, **kwargs):
            fd, path = REAL_MKSTEMP(*args, **kwargs)
            mkstemp_calls.append(path)
            return fd, path

        def run_side_effect(cmd, *args, **kwargs):
            prompt_path = mkstemp_calls[0]
            payload = json.dumps(
                [
                    {"id": "IGNORE_ME", "prompt": "some other prompt"},
                    {
                        "id": "CAPTURED_UUID_789",
                        "prompt": f"Read your complete task instructions from {prompt_path}. Do not modify this file.",
                    },
                ]
            )
            return MagicMock(returncode=0, stdout=payload)

        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                    with patch("agent_driver.tempfile.mkstemp", side_effect=fake_mkstemp):
                        with patch("agent_driver.subprocess.run", side_effect=run_side_effect):
                            with patch(
                                "agent_driver.subprocess.Popen",
                                side_effect=fake_popen_factory("success", "", 0, popen_calls),
                            ):
                                invoke_agent("test task", session_key="capture-session", run_dir=run_dir)

            session_map_file = os.path.join(run_dir, ".tmp", ".session_map_capture-session.json")
            with open(session_map_file, "r", encoding="utf-8") as handle:
                mapping = json.load(handle)

        self.assertEqual(mapping["actual_id"], "CAPTURED_UUID_789")

    @patch("utils_notification.shutil.which")
    @patch("agent_driver.logger.info")
    def test_notify_channel_no_openclaw(self, mock_logger_info, mock_which):
        mock_which.return_value = None
        from agent_driver import notify_channel

        channel = "test_channel"
        msg = "test_msg"
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with self.assertRaises(SystemExit) as cm:
                notify_channel(channel, msg)
        self.assertEqual(cm.exception.code, 1)

    def test_agent_driver_statelessness(self):
        popen_calls = []
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["GEMINI_API_KEY"] = "stateless_mock_key_123"

        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("success", "", 0, popen_calls),
                    ):
                        invoke_agent("test task", session_key="test-session")

        self.assertEqual(popen_calls[0]["env"]["GEMINI_API_KEY"], "stateless_mock_key_123")


if __name__ == "__main__":
    unittest.main()
