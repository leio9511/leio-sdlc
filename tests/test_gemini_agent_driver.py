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

    def test_generic_renderer_preserves_gemini_command_shape(self):
        """TC2: command contains gemini --yolo -p <prompt> --model <model>
        in the agreed order, matching the old Gemini-specific branch behavior."""
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
        # Verify exact command structure: executable, one_shot_args, prompt, model_arg
        self.assertEqual(cmd[0], "/mock/bin/gemini")
        yolo_idx = cmd.index("--yolo")
        p_idx = cmd.index("-p")
        model_idx = cmd.index("--model")
        # Order: --yolo before -p, -p before --model
        self.assertLess(yolo_idx, p_idx)
        self.assertLess(p_idx, model_idx)
        # Prompt is between -p and --model
        prompt_text = cmd[p_idx + 1]
        self.assertTrue(prompt_text.startswith("Read your complete task instructions from"))
        self.assertEqual(cmd[model_idx + 1], "google/gemini-2.0-flash")
        # No extra arguments beyond expected structure
        expected_len = 6  # [exec, --yolo, -p, <prompt>, --model, <model>]
        self.assertEqual(len(cmd), expected_len)

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

    def test_direct_cli_does_not_resume_from_session_map(self):
        """TC5 partial: direct_cli engines ignore existing session_map files (stateless)."""
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
        # Stateless: no -r flag for resume
        self.assertNotIn("-r", cmd)
        # No --list-sessions invocation
        mock_run.assert_not_called()

    def test_direct_cli_does_not_write_session_map_file(self):
        """TC5: after a successful Gemini direct CLI invocation, no .session_map_<session_key>.json is created."""
        popen_calls = []

        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                    with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                        with patch(
                            "agent_driver.subprocess.Popen",
                            side_effect=fake_popen_factory("success", "", 0, popen_calls),
                        ):
                            invoke_agent("test task", session_key="capture-session", run_dir=run_dir)

            session_map_file = os.path.join(run_dir, ".tmp", ".session_map_capture-session.json")
            self.assertFalse(os.path.exists(session_map_file))

    def test_gemini_uses_generic_direct_cli_renderer(self):
        """TC1: with LLM_DRIVER=gemini, command is assembled from gemini_direct_cli.execution;
        no Gemini-specific --list-sessions or resume command is invoked."""
        popen_calls = []
        run_calls = []

        def track_run(cmd, *args, **kwargs):
            run_calls.append(cmd)
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", side_effect=track_run):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("success", "", 0, popen_calls),
                    ):
                        invoke_agent("test task", session_key="test-session")

        cmd = popen_calls[0]["cmd"]
        # Command contains executable from execution spec
        self.assertEqual(cmd[0], "/mock/bin/gemini")
        self.assertIn("--yolo", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)
        # No --list-sessions in the Popen command
        self.assertNotIn("--list-sessions", cmd)
        # No subprocess.run calls should invoke --list-sessions
        for run_cmd in run_calls:
            self.assertNotIn("--list-sessions", run_cmd)

    def test_openclaw_path_does_not_use_generic_direct_cli_renderer(self):
        """TC6: LLM_DRIVER=openclaw still executes through the existing
        OpenClaw-native command construction and writes stateful session mapping."""
        popen_calls = []

        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            with patch.dict(os.environ, {"LLM_DRIVER": "openclaw"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/openclaw"):
                    with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                        with patch("agent_driver.openclaw_agent_exists", return_value=True):
                            with patch("agent_driver.validate_openclaw_agent_model", return_value=None):
                                with patch(
                                    "agent_driver.subprocess.Popen",
                                    side_effect=fake_popen_factory("success", "", 0, popen_calls),
                                ):
                                    invoke_agent("test task", session_key="test-openclaw", run_dir=run_dir)

            cmd = popen_calls[0]["cmd"]
            # OpenClaw uses "agent" subcommand, not one_shot_args
            self.assertIn("agent", cmd)
            self.assertIn("--agent", cmd)
            self.assertIn("--session-id", cmd)
            self.assertIn("-m", cmd)
            # Verify session_map is written for stateful openclaw_native
            session_map_file = os.path.join(run_dir, ".tmp", ".session_map_test-openclaw.json")
            self.assertTrue(os.path.exists(session_map_file))
            with open(session_map_file, "r", encoding="utf-8") as handle:
                mapping = json.load(handle)
            self.assertEqual(mapping["actual_id"], "test-openclaw")

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

    def test_agy_uses_generic_direct_cli_renderer(self):
        """TC4: with LLM_DRIVER=agy, subprocess command invokes mock agy
        through generic renderer and includes --add-dir <workdir> and --print <prompt>."""
        popen_calls = []
        with patch.dict(os.environ, {"LLM_DRIVER": "agy"}, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/agy"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch(
                        "agent_driver.subprocess.Popen",
                        side_effect=fake_popen_factory("agy success", "", 0, popen_calls),
                    ):
                        with stdlib_tempfile.TemporaryDirectory() as workdir:
                            result = invoke_agent("test task", session_key="test-agy", run_dir=workdir)

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.stdout, "agy success")
        cmd = popen_calls[0]["cmd"]
        self.assertEqual(cmd[0], "/mock/bin/agy")
        self.assertIn("--add-dir", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--sandbox", cmd)
        self.assertIn("--print", cmd)
        # Prompt is after --print
        print_idx = cmd.index("--print")
        prompt_arg = cmd[print_idx + 1]
        # Prompt must be a non-empty string; file-indirection mode writes a path reference
        self.assertIsInstance(prompt_arg, str)
        self.assertGreater(len(prompt_arg), 20)
        # No session artifact patterns
        self.assertNotIn("-r", cmd)
        self.assertNotIn("--list-sessions", cmd)

    def test_agy_direct_cli_has_no_session_artifacts(self):
        """TC5: a successful mock agy invocation creates no .session_map_*,
        .coder_session, or .reviewer_session files."""
        popen_calls = []
        with stdlib_tempfile.TemporaryDirectory() as run_dir:
            with patch.dict(os.environ, {"LLM_DRIVER": "agy"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/agy"):
                    with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                        with patch(
                            "agent_driver.subprocess.Popen",
                            side_effect=fake_popen_factory("agy ok", "", 0, popen_calls),
                        ):
                            invoke_agent("test task", session_key="capture-agy", run_dir=run_dir)

            # No session_map_* files
            tmp_dir = os.path.join(run_dir, ".tmp")
            session_map_files = [
                f for f in os.listdir(tmp_dir)
                if f.startswith(".session_map_")
            ] if os.path.isdir(tmp_dir) else []
            self.assertEqual(session_map_files, [])
            # No .coder_session or .reviewer_session at run_dir level
            for artifact in [".coder_session", ".reviewer_session"]:
                self.assertFalse(
                    os.path.exists(os.path.join(run_dir, artifact)),
                    f"{artifact} should not exist for agy direct_cli",
                )

    def test_direct_cli_missing_execution_fails_before_subprocess(self):
        """PR-006 TC5: Invalid direct CLI config (missing execution subsection)
        reports a fatal execution-config error and does not call subprocess.Popen."""
        with stdlib_tempfile.TemporaryDirectory() as sdlc_root:
            config_dir = os.path.join(sdlc_root, "config")
            os.makedirs(config_dir, exist_ok=True)
            # Engine with no execution subsection
            fixture_config = {
                "engines": {
                    "openclaw_native": {
                        "engine_id": "openclaw_native",
                        "cli_alias": "openclaw",
                        "display_name": "OpenClaw Native",
                        "runtime_mode": "openclaw_native",
                        "registration_visibility": "public",
                        "continuity_mode": "stateful",
                        "handle_acquisition_strategy": "unavailable",
                        "fallback_policy": "none",
                        "capability_surface": "runtime_managed",
                    },
                    "broken_cli": {
                        "engine_id": "broken_cli",
                        "cli_alias": "broken",
                        "display_name": "Broken Direct CLI",
                        "runtime_mode": "direct_cli",
                        "registration_visibility": "public",
                        "continuity_mode": "stateless",
                        "handle_acquisition_strategy": "unavailable",
                        "fallback_policy": "fail_closed",
                        "capability_surface": "client_mediated",
                        # Missing: execution subsection causes fail-closed
                    },
                }
            }
            with open(os.path.join(config_dir, "engines.default.json"), "w") as f:
                json.dump(fixture_config, f)

            with patch.dict(os.environ, {"LLM_DRIVER": "broken", "SDLC_ROOT": sdlc_root}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/broken_cli"):
                    with patch("agent_driver.subprocess.run") as mock_run:
                        with patch("agent_driver.subprocess.Popen") as mock_popen:
                            with self.assertRaises(SystemExit) as cm:
                                invoke_agent("test task", session_key="test-broken")

                            # Must fail closed (non-zero exit)
                            self.assertNotEqual(cm.exception.code, 0)
                            # subprocess.Popen must NOT be called
                            mock_popen.assert_not_called()

    def test_direct_cli_model_arg_omitted_when_null(self):
        """TC6: a fixture direct CLI engine with model_arg: null launches
        without any model flag, and default_model is not mandatory."""
        popen_calls = []
        with stdlib_tempfile.TemporaryDirectory() as sdlc_root:
            config_dir = os.path.join(sdlc_root, "config")
            os.makedirs(config_dir, exist_ok=True)
            fixture_config = {
                "engines": {
                    "openclaw_native": {
                        "engine_id": "openclaw_native",
                        "cli_alias": "openclaw",
                        "display_name": "OpenClaw Native",
                        "runtime_mode": "openclaw_native",
                        "registration_visibility": "public",
                        "continuity_mode": "stateful",
                        "handle_acquisition_strategy": "unavailable",
                        "fallback_policy": "none",
                        "capability_surface": "runtime_managed",
                    },
                    "null_model_cli": {
                        "engine_id": "null_model_cli",
                        "cli_alias": "null_model",
                        "display_name": "Null Model CLI",
                        "runtime_mode": "direct_cli",
                        "registration_visibility": "public",
                        "continuity_mode": "stateless",
                        "handle_acquisition_strategy": "unavailable",
                        "fallback_policy": "fail_closed",
                        "capability_surface": "client_mediated",
                        "execution": {
                            "executable": "null_model_cli",
                            "one_shot_args": ["--print"],
                            "model_arg": None,
                            "workspace_arg": None,
                            "permission_args": [],
                            "sandbox_args": [],
                            "timeout_seconds": 300,
                            "env_extra": {},
                        },
                    },
                }
            }
            with open(os.path.join(config_dir, "engines.default.json"), "w") as f:
                json.dump(fixture_config, f)
            # No local config needed

            with patch.dict(os.environ, {"LLM_DRIVER": "null_model", "SDLC_ROOT": sdlc_root}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value="/mock/bin/null_model_cli"):
                    with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                        with patch(
                            "agent_driver.subprocess.Popen",
                            side_effect=fake_popen_factory("ok", "", 0, popen_calls),
                        ):
                            invoke_agent("test task", session_key="test-null-model")

            cmd = popen_calls[0]["cmd"]
            # No model flag anywhere in the command
            self.assertNotIn("--model", cmd)
            self.assertNotIn("-m", cmd)
            # Must still contain the executable and one_shot_args
            self.assertEqual(cmd[0], "/mock/bin/null_model_cli")
            self.assertIn("--print", cmd)


if __name__ == "__main__":
    unittest.main()
