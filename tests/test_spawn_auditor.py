import os
import sys
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock
import subprocess

# Add scripts directory to path to allow import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import spawn_auditor

def test_spawn_auditor_missing_channel(capsys):
    # Missing required argument will cause argparse to exit with code 2
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md", "--workdir", "."]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        assert e.value.code == 2

@patch("subprocess.run")
def test_spawn_auditor_invalid_channel_handshake_fail(mock_run, capsys):
    # Simulate a failed handshake from the openclaw cli
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "Invalid channel format"
    
    os.environ["SDLC_TEST_MODE"] = "false"
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md", "--workdir", ".", "--channel", "invalid_format"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid notification channel format or failed handshake." in captured.out

def test_spawn_auditor_guardrail(capsys):
    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", "dummy.md", "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "Startup validation failed" in captured.out

@patch("agent_driver.notify_channel")
def test_spawn_auditor_valid_channel_success(mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"Dummy PRD")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    os.environ["MOCK_AUDIT_RESULT"] = "APPROVE"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        spawn_auditor.main()
        
    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out
    
    mock_notify.assert_called_with("test_channel", "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": prd_file})
    os.remove(prd_file)

@patch("agent_driver.notify_channel")
def test_spawn_auditor_valid_channel_reject(mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"Dummy PRD")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    os.environ["MOCK_AUDIT_RESULT"] = "REJECT"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        spawn_auditor.main()
        
    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
    
    mock_notify.assert_called_with("test_channel", "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": prd_file})
    os.remove(prd_file)
