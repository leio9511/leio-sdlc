import os
import json
import pytest
import tempfile
import sys

# Ensure scripts directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
from utils_api_key import assign_gemini_api_key

def test_no_keys_configured():
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        state_file_path = tf.name
    try:
        # No keys configured, should return None
        res = assign_gemini_api_key("session_123", {"gemini_api_keys": []}, state_file_path)
        assert res is None
        
        # Or missing entirely
        res = assign_gemini_api_key("session_123", {}, state_file_path)
        assert res is None
    finally:
        os.remove(state_file_path)

def test_first_assignment_persists():
    keys = ["key_A_12345678", "key_B_abcdefgh", "key_C_11112222"]
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        state_file_path = tf.name
    try:
        res = assign_gemini_api_key("session_123", {"gemini_api_keys": keys}, state_file_path)
        assert res in keys
        
        # Verify persistence
        with open(state_file_path, "r") as f:
            state = json.load(f)
        
        assert "session_123" in state
        assert state["session_123"] == res[-8:]
    finally:
        os.remove(state_file_path)

def test_anti_drift_stickiness():
    keys_initial = ["key_A_12345678", "key_B_abcdefgh", "key_C_11112222"]
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        state_file_path = tf.name
    try:
        res1 = assign_gemini_api_key("session_xyz", {"gemini_api_keys": keys_initial}, state_file_path)
        assert res1 in keys_initial
        
        # Modify the order
        keys_modified = ["key_C_11112222", "key_A_12345678", "key_B_abcdefgh"]
        res2 = assign_gemini_api_key("session_xyz", {"gemini_api_keys": keys_modified}, state_file_path)
        
        assert res1 == res2
    finally:
        os.remove(state_file_path)

def test_graceful_degradation():
    keys_initial = ["key_A_12345678", "key_B_abcdefgh", "key_C_11112222"]
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        state_file_path = tf.name
    try:
        res1 = assign_gemini_api_key("session_xyz", {"gemini_api_keys": keys_initial}, state_file_path)
        assert res1 in keys_initial
        
        # Remove the assigned key
        keys_missing = [k for k in keys_initial if k != res1]
        
        res2 = assign_gemini_api_key("session_xyz", {"gemini_api_keys": keys_missing}, state_file_path)
        
        assert res2 in keys_missing
        assert res2 != res1
        
        # Verify it updated the file
        with open(state_file_path, "r") as f:
            state = json.load(f)
        
        assert state["session_xyz"] == res2[-8:]
    finally:
        os.remove(state_file_path)
