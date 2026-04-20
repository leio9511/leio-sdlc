import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from utils_api_key import get_api_keys_from_config, assign_gemini_api_key, get_env_with_gemini_key

def test_api_key_extraction():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump({"gemini_api_keys": ["key1_fingerprintA", "key2_fingerprintB"]}, f)
        config_path = f.name
        
    keys = get_api_keys_from_config(config_path)
    assert keys == ["key1_fingerprintA", "key2_fingerprintB"]
    
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as state_f:
        state_path = state_f.name
        
    session_key = "test_session_1"
    assigned1 = assign_gemini_api_key(session_key, keys, state_path)
    assert assigned1 in keys
    
    # Should get the same key because of session stickiness
    assigned2 = assign_gemini_api_key(session_key, keys, state_path)
    assert assigned1 == assigned2
    
    os.remove(config_path)
    os.remove(state_path)

def test_orchestrator_uses_utils_api_key():
    import orchestrator
    assert hasattr(orchestrator, "get_env_with_gemini_key")
    assert hasattr(orchestrator, "assign_gemini_api_key")
    
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as state_f:
        state_path = state_f.name
        
    global_dir = os.path.dirname(os.path.dirname(state_path))
    keys = ["key_A", "key_B"]
    
    with patch("utils_api_key.assign_gemini_api_key", return_value="key_A") as mock_assign:
        env = orchestrator.get_env_with_gemini_key("test_sess", keys, global_dir)
        mock_assign.assert_called_once()
        assert env["GEMINI_API_KEY"] == "key_A"
        
    os.remove(state_path)
