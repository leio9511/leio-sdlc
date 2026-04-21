import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import json

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
import config
from agent_driver import invoke_agent, AgentResult

class TestGeminiAgentDriver(unittest.TestCase):
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_invoke_agent_returns_agentresult(self, mock_resolve_cmd, mock_run, mock_exists):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="test stdout", stderr="test stderr")
        mock_exists.return_value = False
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        
        with patch.dict(os.environ, env):
            with patch("agent_driver.tempfile.mkstemp", return_value=(3, "/tmp/fake.txt")):
                with patch("agent_driver.os.fdopen", mock_open()):
                    with patch("agent_driver.os.chmod"):
                        with patch("agent_driver.os.remove"):
                            result = invoke_agent("test task", session_key="test-session")
                            
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
        self.assertEqual(result.stdout, "test stdout")
        self.assertEqual(result.stderr, "test stderr")
        self.assertEqual(result.return_code, 0)
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_gemini_driver_constructs_correct_cmd(self, mock_resolve_cmd, mock_run, mock_exists):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        mock_exists.return_value = False
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["SDLC_MODEL"] = "google/gemini-2.0-flash"
        
        with patch.dict(os.environ, env):
            invoke_agent("test task", session_key="test-session")
            
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args_list[0][0][0]
        
        self.assertIn("--yolo", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)
        self.assertEqual(cmd[0], "/mock/bin/gemini")
        
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "google/gemini-2.0-flash")

    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_gemini_driver_env_var_priority(self, mock_resolve_cmd, mock_run, mock_exists):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        mock_exists.return_value = False
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["TEST_MODEL"] = "fallback-model"
        env["SDLC_MODEL"] = "priority-model"
        
        with patch.dict(os.environ, env):
            invoke_agent("test task", session_key="test-session")
            
        cmd = mock_run.call_args_list[0][0][0]
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], "priority-model")
        
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_config_externalization(self, mock_resolve_cmd, mock_run, mock_exists):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        mock_exists.return_value = False
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        if "SDLC_MODEL" in env:
            del env["SDLC_MODEL"]
        if "TEST_MODEL" in env:
            del env["TEST_MODEL"]
            
        with patch.dict(os.environ, env):
            invoke_agent("test task", session_key="test-session")
            
        cmd = mock_run.call_args_list[0][0][0]
        model_idx = cmd.index("--model")
        self.assertEqual(cmd[model_idx + 1], config.DEFAULT_GEMINI_MODEL)
        self.assertEqual(config.DEFAULT_GEMINI_MODEL, "gemini-3.1-pro-preview")
        
    @patch("agent_driver.os.makedirs")
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.tempfile.mkstemp")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_invoke_agent_with_run_dir(self, mock_resolve_cmd, mock_run, mock_mkstemp, mock_exists, mock_makedirs):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        
        def fake_exists(path):
            if path == "/mock/run_dir":
                return True
            return False
        mock_exists.side_effect = fake_exists
        mock_mkstemp.return_value = (3, "/mock/run_dir/.tmp/sdlc_prompt_123.txt")
        
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            with patch("agent_driver.os.fdopen", mock_open()):
                with patch("agent_driver.os.chmod"):
                    with patch("agent_driver.os.remove"):
                        result = invoke_agent("test task", session_key="test-session", run_dir="/mock/run_dir")
                        
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
                        
        mock_makedirs.assert_any_call("/mock/run_dir/.tmp", exist_ok=True)
        mock_mkstemp.assert_called_with(suffix=".txt", prefix="sdlc_prompt_test-session_", dir="/mock/run_dir/.tmp", text=True)

    @patch("agent_driver.os.makedirs")
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.tempfile.gettempdir")
    @patch("agent_driver.tempfile.mkstemp")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_invoke_agent_fallback_tempdir(self, mock_resolve_cmd, mock_run, mock_mkstemp, mock_gettempdir, mock_exists, mock_makedirs):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        mock_gettempdir.return_value = "/mock/system/tmp"
        
        def fake_exists(path):
            return False
        mock_exists.side_effect = fake_exists
        mock_mkstemp.return_value = (3, "/mock/system/tmp/sdlc_prompt_123.txt")
        
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            with patch("agent_driver.os.fdopen", mock_open()):
                with patch("agent_driver.os.chmod"):
                    with patch("agent_driver.os.remove"):
                        result = invoke_agent("test task", session_key="test-session", run_dir="/mock/nonexistent")
                        
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-session")
                        
        mock_makedirs.assert_any_call("/mock/system/tmp", exist_ok=True)
        mock_mkstemp.assert_called_with(suffix=".txt", prefix="sdlc_prompt_test-session_", dir="/mock/system/tmp", text=True)

    @patch("agent_driver.tempfile.mkstemp")
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_file_indirection_prompt_format(self, mock_resolve_cmd, mock_run, mock_exists, mock_mkstemp):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        mock_exists.return_value = False
        mock_mkstemp.return_value = (3, "/mock/tmp/sdlc_prompt_123.txt")
        
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            # We must mock os.fdopen so it doesn't fail on fake fd
            with patch("agent_driver.os.fdopen", mock_open()):
                with patch("agent_driver.os.chmod"):
                    with patch("agent_driver.os.remove"):
                        invoke_agent("test task", session_key="test-session")
            
        cmd = mock_run.call_args_list[0][0][0]
        p_idx = cmd.index("-p")
        prompt_arg = cmd[p_idx + 1]
        self.assertEqual(prompt_arg, "Read your complete task instructions from /mock/tmp/sdlc_prompt_123.txt. Do not modify this file.")

    @patch("builtins.open", new_callable=mock_open, read_data='{"actual_id": "RESUMED_UUID_456"}')
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_lock_free_session_resume(self, mock_resolve_cmd, mock_run, mock_exists, mock_file):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="success")
        
        # Make os.path.exists return True for the session map file
        def fake_exists(path):
            if ".session_map_test-session.json" in path:
                return True
            return False
        mock_exists.side_effect = fake_exists
        
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            with patch("agent_driver.tempfile.mkstemp", return_value=(3, "/tmp/fake.txt")):
                with patch("agent_driver.os.fdopen", mock_open()):
                    with patch("agent_driver.os.chmod"):
                        with patch("agent_driver.os.remove"):
                            invoke_agent("test task", session_key="test-session")
                            
        cmd = mock_run.call_args_list[0][0][0]
        self.assertIn("-r", cmd)
        r_idx = cmd.index("-r")
        self.assertEqual(cmd[r_idx + 1], "RESUMED_UUID_456")

    @patch("builtins.open", new_callable=mock_open)
    @patch("agent_driver.tempfile.mkstemp")
    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_session_uuid_capture(self, mock_resolve_cmd, mock_run, mock_exists, mock_mkstemp, mock_file):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        
        # First call is the gemini run, second call is the list-sessions
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="success"),
            MagicMock(returncode=0, stdout=json.dumps([
                {"id": "IGNORE_ME", "prompt": "some other prompt"},
                {"id": "CAPTURED_UUID_789", "prompt": "Read your complete task instructions from /mock/tmp/sdlc_prompt_capture.txt."}
            ]))
        ]
        
        mock_exists.return_value = False
        mock_mkstemp.return_value = (3, "/mock/tmp/sdlc_prompt_capture.txt")
        
        with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}):
            with patch("agent_driver.os.fdopen", mock_open()):
                with patch("agent_driver.os.chmod"):
                    with patch("agent_driver.os.remove"):
                        invoke_agent("test task", session_key="capture-session")
                        
        # Check if list-sessions was called
        self.assertEqual(mock_run.call_count, 2)
        list_cmd = mock_run.call_args_list[1][0][0]
        self.assertIn("--list-sessions", list_cmd)
        
        # Check if open was called to write the mapping
        write_calls = [c for c in mock_file.mock_calls if "write" in str(c)]
        written_data = "".join(c[1][0] for c in write_calls)
        self.assertIn('"actual_id": "CAPTURED_UUID_789"', written_data)

    @patch("agent_driver.shutil.which")
    @patch("agent_driver.logger.info")
    def test_notify_channel_no_openclaw(self, mock_logger_info, mock_which):
        mock_which.return_value = None
        from agent_driver import notify_channel
        channel = "test_channel"
        msg = "test_msg"
        expected_msg = f"🤖 [SDLC Engine] {msg}"
        with self.assertRaises(SystemExit) as cm:
            notify_channel(channel, msg)
        self.assertEqual(cm.exception.code, 1)


    @patch("agent_driver.os.path.exists")
    @patch("agent_driver.subprocess.run")
    @patch("agent_driver.resolve_cmd")
    def test_agent_driver_statelessness(self, mock_resolve_cmd, mock_run, mock_exists):
        mock_resolve_cmd.return_value = "/mock/bin/gemini"
        mock_run.return_value = MagicMock(returncode=0, stdout="success")
        mock_exists.return_value = False
        
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["GEMINI_API_KEY"] = "stateless_mock_key_123"
        
        with patch.dict(os.environ, env):
            with patch("agent_driver.tempfile.mkstemp", return_value=(3, "/tmp/fake.txt")):
                with patch("agent_driver.os.fdopen", mock_open()):
                    with patch("agent_driver.os.chmod"):
                        with patch("agent_driver.os.remove"):
                            invoke_agent("test task", session_key="test-session")
                            
        self.assertTrue(mock_run.called)
        # Verify subprocess.run was called natively inheriting the environment
        # (env parameter is not explicitly passed, meaning it uses os.environ)
        kwargs = mock_run.call_args_list[0][1]
        self.assertIn("env", kwargs)
        
        # (env parameter is not explicitly passed, meaning it uses os.environ)

if __name__ == "__main__":
    unittest.main()
