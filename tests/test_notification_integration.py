import sys
import os
import subprocess
import argparse
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator
from openclaw_mock_support import provision_fake_openclaw

def test_notify_channel_integration(monkeypatch):
    monkeypatch.delenv("SDLC_TEST_MODE", raising=False)
    
    with provision_fake_openclaw() as (temp_bin, get_calls):
        # Test with a simple channel ID
        orchestrator.notify_channel("C123", "", "sdlc_start", {"prd_id": "PRD_081_test.md"})
        
        calls = get_calls()
        assert len(calls) == 1
        called_args = calls[0]
        # Verify the command structure for a simple channel ID
        # The first argument is the executable, so args[1:5]
        assert called_args[1:5] == ["message", "send", "-t", "C123"]
        assert "🚀 1. [prd-081] SDLC 启动" in called_args[6]

        # Test with a complex routing key
        orchestrator.notify_channel("slack:channel:C456", "test message")
        calls = get_calls()
        assert len(calls) == 2
        called_args = calls[1]
        assert called_args[1:7] == ["message", "send", "--channel", "slack", "-t", "channel:C456"]
        assert "test message" in called_args[8]
