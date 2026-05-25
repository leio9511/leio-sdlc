import os
import json
import re

class RegistryValidationError(Exception):
    def __init__(self, message):
        prefix = "[FATAL] Engine Registry validation failed."
        msg = message if message.startswith(prefix) else f"{prefix} {message}"
        super().__init__(msg)

SENSITIVE_KEYS = {
    "executable_path",
    "launch_arguments",
    "custom_env_vars",
    "private_endpoint",
    "launch_command"
}

def _extract_sensitive_values(text):
    """Extract string values associated with sensitive keys from raw JSON text."""
    sensitive_values = set()
    for key in SENSITIVE_KEYS:
        # Match string values: "key": "value"
        for match in re.finditer(f'"{key}"\\s*:\\s*"([^"]+)"', text):
            if match.group(1):
                sensitive_values.add(match.group(1))
        # Match array of strings: "key": ["val1", "val2"]
        for match in re.finditer(f'"{key}"\\s*:\\s*\\[(.*?)\\]', text, re.DOTALL):
            for str_match in re.finditer(r'"([^"]+)"', match.group(1)):
                if str_match.group(1):
                    sensitive_values.add(str_match.group(1))
        # Match dict of strings: "key": {"k": "v"}
        for match in re.finditer(f'"{key}"\\s*:\\s*\\{{(.*?)\\}}', text, re.DOTALL):
            for str_match in re.finditer(r'"([^"]+)"', match.group(1)):
                if str_match.group(1):
                    sensitive_values.add(str_match.group(1))
    return sensitive_values

REQUIRED_ENGINE_FIELDS = [
    "engine_id",
    "display_name",
    "runtime_mode",
    "registration_visibility",
    "continuity_mode",
    "handle_acquisition_strategy",
    "fallback_policy",
    "capability_surface"
]

ALLOWED_REGISTRATION_VISIBILITY_VALUES = {"public", "local_private"}
ALLOWED_RUNTIME_MODE_VALUES = {"openclaw_native", "direct_cli", "acp"}
ALLOWED_CONTINUITY_MODE_VALUES = {"authoritative_resume", "unsupported"}
ALLOWED_HANDLE_ACQUISITION_STRATEGY_VALUES = {"protocol_native", "explicit_returned_handle", "unavailable"}
ALLOWED_FALLBACK_POLICY_VALUES = {"none", "legacy_direct_cli", "fail_closed_until_prerequisite_ready"}

def _scrub_config(data):
    if isinstance(data, dict):
        scrubbed = {}
        for k, v in data.items():
            if k in SENSITIVE_KEYS:
                scrubbed[k] = "[REDACTED]"
            else:
                scrubbed[k] = _scrub_config(v)
        return scrubbed
    elif isinstance(data, list):
        return [_scrub_config(item) for item in data]
    return data

def _check_no_sensitive_keys(data, source):
    # Reject public defaults containing sensitive fields
    if isinstance(data, dict):
        for k, v in data.items():
            if k in SENSITIVE_KEYS:
                raise RegistryValidationError(f"Public default {source} contains sensitive field '{k}'")
            _check_no_sensitive_keys(v, source)
    elif isinstance(data, list):
        for item in data:
            _check_no_sensitive_keys(item, source)

def _merge_and_validate(default_config, local_config):
    if "engines" not in default_config or not isinstance(default_config["engines"], dict):
        raise ValueError("default config must contain an 'engines' map at the top level")
    
    registry = {"engines": {}}
    
    for k, v in default_config["engines"].items():
        registry["engines"][k] = v.copy() if isinstance(v, dict) else v
        
    if local_config:
        if "engines" not in local_config or not isinstance(local_config["engines"], dict):
            raise ValueError("local config must contain an 'engines' map at the top level")
            
        for engine_id, local_entry in local_config["engines"].items():
            if not isinstance(local_entry, dict):
                raise ValueError(f"Engine entry {engine_id} must be a dictionary")
                
            if engine_id in registry["engines"]:
                default_entry = registry["engines"][engine_id]
                original_visibility = default_entry.get("registration_visibility")
                
                # Field-level shallow merge
                for k, v in local_entry.items():
                    default_entry[k] = v
                
                if original_visibility == "public" and default_entry.get("registration_visibility") == "local_private":
                    raise ValueError(f"Local override is not allowed to change public engine '{engine_id}' visibility to local_private")
            else:
                new_entry = local_entry.copy()
                if new_entry.get("registration_visibility") == "public":
                    raise ValueError(f"New local engine '{engine_id}' cannot be public")
                new_entry["registration_visibility"] = "local_private"
                registry["engines"][engine_id] = new_entry
                
    for map_key, entry in registry["engines"].items():
        if map_key != entry.get("engine_id"):
            raise ValueError(f"Outer map key '{map_key}' does not match engine_id '{entry.get('engine_id')}'")
            
        for req_field in REQUIRED_ENGINE_FIELDS:
            if req_field not in entry:
                raise ValueError(f"Engine '{map_key}' is missing required field '{req_field}': {_scrub_config(entry)}")
                
        if not isinstance(entry["capability_surface"], str) or not entry["capability_surface"]:
            raise ValueError(f"Engine '{map_key}' must have a non-empty string capability_surface: {_scrub_config(entry)}")
            
        if entry["registration_visibility"] not in ALLOWED_REGISTRATION_VISIBILITY_VALUES:
            raise ValueError(f"Invalid registration_visibility: {entry['registration_visibility']} in {_scrub_config(entry)}")
            
        if entry["runtime_mode"] not in ALLOWED_RUNTIME_MODE_VALUES:
            raise ValueError(f"Invalid runtime_mode: {entry['runtime_mode']} in {_scrub_config(entry)}")
            
        if entry["continuity_mode"] not in ALLOWED_CONTINUITY_MODE_VALUES:
            raise ValueError(f"Invalid continuity_mode: {entry['continuity_mode']} in {_scrub_config(entry)}")
            
        if entry["handle_acquisition_strategy"] not in ALLOWED_HANDLE_ACQUISITION_STRATEGY_VALUES:
            raise ValueError(f"Invalid handle_acquisition_strategy: {entry['handle_acquisition_strategy']} in {_scrub_config(entry)}")
            
        if entry["fallback_policy"] not in ALLOWED_FALLBACK_POLICY_VALUES:
            raise ValueError(f"Invalid fallback_policy: {entry['fallback_policy']} in {_scrub_config(entry)}")
            
    return registry

def load_engine_registry(sdlc_root):
    default_path = os.path.join(sdlc_root, "config", "engines.default.json")
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")

    sensitive_values = set()
    
    def _read_and_extract(path):
        with open(path, "r") as f:
            content = f.read()
            sensitive_values.update(_extract_sensitive_values(content))
            return content

    try:
        try:
            default_content = _read_and_extract(default_path)
            default_config = json.loads(default_content)
        except json.JSONDecodeError as e:
            raise RegistryValidationError(f"engines.default.json is malformed: {e}")

        _check_no_sensitive_keys(default_config, "engines.default.json")
        
        local_config = None
        if os.path.exists(local_path):
            if os.path.getsize(local_path) == 0:
                raise RegistryValidationError("engines.local.json is a zero-byte file")
            local_content = _read_and_extract(local_path)
            try:
                local_config = json.loads(local_content)
            except json.JSONDecodeError as e:
                # Add the raw JSON into the exception to prove scrubbing works if it were exposed
                raise RegistryValidationError(f"engines.local.json is malformed: {e}")

        merged_config = _merge_and_validate(default_config, local_config)
        return merged_config
    except Exception as e:
        error_msg = str(e)
        for val in sensitive_values:
            error_msg = error_msg.replace(val, "[REDACTED]")
            
        if isinstance(e, RegistryValidationError):
            if str(e) != error_msg:
                raise RegistryValidationError(error_msg) from None
            raise e
        else:
            raise RegistryValidationError(error_msg) from None
