import os
import sys
import importlib
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

import config
from utils_notification import (
    StdoutProvider,
    OpenClawBridgeProvider,
    NotificationRouter,
    send_ignition_handshake
)

def test_runtime_dir_defaults_to_openclaw_skills():
    with patch.dict(os.environ, {}, clear=True):
        importlib.reload(config)
        expected = os.path.expanduser("~/.openclaw/skills")
        assert config.SDLC_RUNTIME_DIR == expected

def test_runtime_dir_uses_environment_override():
    with patch.dict(os.environ, {"SDLC_RUNTIME_DIR": "/custom/path/to/runtime"}):
        importlib.reload(config)
        assert config.SDLC_RUNTIME_DIR == "/custom/path/to/runtime"

def test_notification_router_stdout_provider_prefix(capsys):
    provider = StdoutProvider()
    provider.send("stdout", "Hello world")
    captured = capsys.readouterr()
    assert "[NOTIFY] Hello world" in captured.out

def test_notification_router_missing_bridge_exits_fatally(capsys):
    import utils_notification
    
    with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
        with patch.object(utils_notification.config, "NOTIFICATION_BRIDGE_BINARY", "missing_binary_that_does_not_exist_123"):
            provider = OpenClawBridgeProvider()
            with pytest.raises(SystemExit) as exc:
                provider.send("slack:C123", "Test message")
                
            assert exc.value.code == 1
            captured = capsys.readouterr()
            expected_error = "[FATAL] Requested remote channel 'slack:C123' but the required message-delivery tool 'missing_binary_that_does_not_exist_123' was not found in PATH."
            assert expected_error in captured.err

def test_send_ignition_handshake_uses_exact_template(capsys):
    # Route through stdout to capture the emitted template easily
    send_ignition_handshake("stdout")
    captured = capsys.readouterr()
    assert "🤝 [SDLC Engine] Initial Handshake successful. Channel linked." in captured.out

def test_notify_channel_routes_event_messages_through_router(capsys):
    from agent_driver import notify_channel
    with patch.dict(os.environ, {"SDLC_NOTIFICATION_VERSION": "2"}):
        notify_channel("stdout", "Test Message", "sdlc_handshake")
        captured = capsys.readouterr()
        assert "[NOTIFY] 🤝 [SDLC Engine] Initial Handshake successful. Channel linked." in captured.out

def test_orchestrator_ignition_handshake_uses_central_router():
    import orchestrator
    with patch("orchestrator.drun", return_value=MagicMock(stdout="", returncode=0)):
        with patch("orchestrator.validate_prd_is_committed"):
            with patch("orchestrator.get_mainline_branch", return_value="master"):
                with patch("orchestrator.acquire_global_locks", return_value=([], [])):
                    with patch("fcntl.flock"):
                        with patch("agent_driver.send_ignition_handshake", side_effect=SystemExit(1)) as mock_handshake:
                            with patch.object(sys, 'argv', ["orchestrator.py", "--channel", "invalid:channel", "--prd-file", "test.md", "--workdir", ".", "--enable-exec-from-workspace", "--force-replan", "false"]):
                                with patch.dict(os.environ, {"SDLC_BYPASS_BRANCH_CHECK": "1"}):
                                    with pytest.raises(SystemExit) as exc:
                                        orchestrator.main()
                                    assert exc.value.code == 1
                                    mock_handshake.assert_called_once_with("invalid:channel")



@patch("spawn_reviewer.subprocess.run")
@patch("spawn_reviewer.resolve_cmd")
def test_spawn_reviewer_system_alert_uses_dynamic_command_resolution(mock_resolve_cmd, mock_run):
    import spawn_reviewer
    
    mock_resolve_cmd.return_value = "/dummy_runtime_dir/openclaw/openclaw"
    mock_run.return_value.returncode = 0
    
    test_args = ["spawn_reviewer.py", "--system-alert", "Alert message", "--enable-exec-from-workspace", "--run-dir", "/tmp/reviewer_test"]
    
    with patch("sys.argv", test_args):
        with patch("spawn_reviewer.os.path.exists", return_value=True), \
             patch("spawn_reviewer.open", create=True) as mock_open:

            mock_open.return_value.__enter__.return_value.read.return_value = "dummy-session-id"
            with patch.dict("os.environ", {"SDLC_TEST_MODE": "false"}):
                try:
                    spawn_reviewer.main()
                except SystemExit:
                    pass

                mock_resolve_cmd.assert_called()
                called_cmd = mock_run.call_args[0][0]
                assert called_cmd[0] == "/dummy_runtime_dir/openclaw/openclaw"
                assert "dummy-session-id" in called_cmd
                assert "Alert message" in called_cmd
