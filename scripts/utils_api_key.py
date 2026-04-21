import os
import json
import hashlib
from lock_utils import FileLock, WorkspaceLockException

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
                except json.JSONDecodeError:
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
    except (OSError, WorkspaceLockException):
        # Graceful degradation for IO/Lock errors
        return None

def setup_spawner_api_key(args, script_file):
    try:
        config_path = os.path.abspath(os.path.join(os.path.dirname(script_file), "..", "config", "sdlc_config.json"))
        app_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    app_config = json.load(f)
            except json.JSONDecodeError:
                pass

        global_dir = os.path.abspath(os.path.join(os.path.dirname(script_file), ".."))
        session_keys_path = os.path.join(global_dir, ".sdlc_runs", ".session_keys.json")
        session_name = os.path.basename(script_file).replace(".py", "")
        pr_file_val = getattr(args, "pr_file", None)
        if pr_file_val:
            session_name += "_" + os.path.basename(pr_file_val)

        assigned_key = assign_gemini_api_key(session_name, app_config, session_keys_path)
        if assigned_key and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = assigned_key
    except (OSError, AttributeError):
        pass

