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
    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", "dummy.md", "--workdir", "."]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "[ACTION REQUIRED FOR MANAGER] [FATAL] Channel handshake failed. You MUST provide a valid --channel parameter" in captured.out

@patch("agent_driver.notify_channel")
def test_spawn_auditor_valid_channel_success(mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"Dummy PRD")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    os.environ["MOCK_AUDIT_RESULT"] = "APPROVE"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
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
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        spawn_auditor.main()
        
    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
    
    mock_notify.assert_called_with("test_channel", "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": prd_file})
    os.remove(prd_file)
