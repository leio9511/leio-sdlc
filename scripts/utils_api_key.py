import os
import json
import hashlib
from lock_utils import FileLock

def assign_gemini_api_key(session_key, config, session_keys_path):
    gemini_api_keys = config.get("gemini_api_keys", [])
    if not gemini_api_keys:
        return None
        
    os.makedirs(os.path.dirname(session_keys_path), exist_ok=True)
    
    lock_path = session_keys_path + ".lock"
    try:
        with FileLock(lock_path):
            state = {}
            if os.path.exists(session_keys_path):
                try:
                    with open(session_keys_path, "r") as f:
                        state = json.load(f)
                except Exception:
                    pass
                    
            fingerprint = state.get(session_key)
            
            if fingerprint:
                for key in gemini_api_keys:
                    if key.endswith(fingerprint):
                        return key
                        
            idx = int(hashlib.md5(session_key.encode("utf-8")).hexdigest(), 16) % len(gemini_api_keys)
            selected_key = gemini_api_keys[idx]
            new_fingerprint = selected_key[-8:] if len(selected_key) >= 8 else selected_key
            
            state[session_key] = new_fingerprint
            
            with open(session_keys_path, "w") as f:
                json.dump(state, f, indent=2)
                
            return selected_key
    except Exception:
        # Graceful degradation
        return None
