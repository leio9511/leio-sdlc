import os
import sys
import importlib
import pytest
from unittest.mock import patch, MagicMock

import scripts.config as config
from scripts.utils_notification import (
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
