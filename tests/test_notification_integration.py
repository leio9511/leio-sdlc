import sys
import os
import subprocess
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from orchestrator import notify_channel

def test_notify_channel_integration(monkeypatch):
    calls = []
    def mock_run(*args, **kwargs):
        calls.append(args[0])

    monkeypatch.setattr(subprocess, 'run', mock_run)
    
    args = argparse.Namespace(notify_channel='C123', notify_target='T123')
    notify_channel(args, "", "sdlc_start", {"prd_id": "PRD_081_test.md"})
    
    assert len(calls) == 1
    called_args = calls[0]
    assert called_args[0:7] == ["openclaw", "message", "send", "--channel", "C123", "--target", "T123"]
    assert "🚀 1. [prd-081] SDLC 启动" in called_args[8]
