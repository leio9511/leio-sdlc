import unittest
import os
import json
import tempfile
import shutil
from scripts.utils_api_key import assign_gemini_api_key

class TestUtilsApiKey(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.session_keys_path = os.path.join(self.temp_dir, ".session_keys.json")
        self.config = {
            "gemini_api_keys": ["KEY1_12345678", "KEY2_87654321"]
        }
        
    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_assign_api_key_creates_sticky_mapping(self):
        session_key = "test_session_1"
        assigned_key = assign_gemini_api_key(session_key, self.config, self.session_keys_path)
        self.assertIn(assigned_key, self.config["gemini_api_keys"])
        
        # Verify it created the mapping
        self.assertTrue(os.path.exists(self.session_keys_path))
        with open(self.session_keys_path, "r") as f:
            state = json.load(f)
            self.assertIn(session_key, state)
            # The fingerprint should match the assigned key's end
            self.assertTrue(assigned_key.endswith(state[session_key]))
            
        # Calling again should return the same key
        assigned_key_2 = assign_gemini_api_key(session_key, self.config, self.session_keys_path)
        self.assertEqual(assigned_key, assigned_key_2)

    def test_assign_api_key_no_keys_in_config(self):
        session_key = "test_session_2"
        assigned_key = assign_gemini_api_key(session_key, {}, self.session_keys_path)
        self.assertIsNone(assigned_key)

if __name__ == '__main__':
    unittest.main()
