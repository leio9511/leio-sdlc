import os
import json
import fcntl
import hashlib

def get_api_keys_from_config(config_path):
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                app_config_data = json.load(f)
                return app_config_data.get("gemini_api_keys", [])
        except Exception:
            pass
    return []

def assign_gemini_api_key(session_key, gemini_api_keys, state_file_path):
    if not gemini_api_keys:
        return None
        
    os.makedirs(os.path.dirname(state_file_path), exist_ok=True)
    try:
        fd = os.open(state_file_path, os.O_CREAT | os.O_RDWR)
    except Exception:
        # Graceful degradation if file cannot be opened
        return None
        
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        
        state = {}
        try:
            file_size = os.fstat(fd).st_size
            if file_size > 0:
                os.lseek(fd, 0, os.SEEK_SET)
                content = os.read(fd, file_size).decode('utf-8')
                state = json.loads(content)
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
        
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps(state, indent=2).encode('utf-8'))
        
        return selected_key
        
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

def get_env_with_gemini_key(session_key, gemini_api_keys, global_dir):
    env = os.environ.copy()
    if not gemini_api_keys:
        return env
        
    state_file_path = os.path.join(global_dir, ".sdlc_runs", ".session_keys.json")
    assigned_key = assign_gemini_api_key(session_key, gemini_api_keys, state_file_path)
    if assigned_key:
        env["GEMINI_API_KEY"] = assigned_key
    return env

