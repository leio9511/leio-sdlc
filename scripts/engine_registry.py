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

def _redact_raw_json(text):
    """Redact string values associated with sensitive keys directly in raw JSON text."""
    redacted = text
    for key in SENSITIVE_KEYS:
        # 1. Redact simple string values (handles escaped quotes and missing closing quote)
        redacted = re.sub(
            r'("' + key + r'"\s*:\s*)"(?:[^"\\\n]|\\.)*(?:"?)',
            r'\1"[REDACTED]"',
            redacted
        )
        
        # 2. Redact array string values
        def repl_array(m):
            content = m.group(2)
            content_redacted = re.sub(r'"(?:[^"\\\n]|\\.)*(?:"?)', '"[REDACTED]"', content)
            return m.group(1) + content_redacted + m.group(3)
            
        redacted = re.sub(
            r'("' + key + r'"\s*:\s*\[)(.*?)(\]|\Z)',
            repl_array,
            redacted,
            flags=re.DOTALL
        )
        
        # 3. Redact dict string values
        def repl_dict(m):
            content = m.group(2)
            content_redacted = re.sub(r'("[^"]+"\s*:\s*)"(?:[^"\\\n]|\\.)*(?:"?)', r'\1"[REDACTED]"', content)
            return m.group(1) + content_redacted + m.group(3)
            
        redacted = re.sub(
            r'("' + key + r'"\s*:\s*\{)(.*?)(\}|\Z)',
            repl_dict,
            redacted,
            flags=re.DOTALL
        )
        
        # 4. Catch-all for unquoted values on the same line
        redacted = re.sub(
            r'("' + key + r'"\s*:\s*)(?![ \t\r\n]*["\[\{])([^,\n\}]+)',
            r'\1"[REDACTED]"',
            redacted
        )
        
    return redacted

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
# continuity_mode (str): "stateful" - engine natively returns a stable, authoritative,
# non-heuristic continuation handle with contractual guarantees.
# "stateless" - every invocation is independent one-shot; any continuation is
# provided by the orchestrator through explicit context injection.
ALLOWED_CONTINUITY_MODE_VALUES = {"stateful", "stateless"}
ALLOWED_HANDLE_ACQUISITION_STRATEGY_VALUES = {"protocol_native", "explicit_returned_handle", "unavailable"}
ALLOWED_FALLBACK_POLICY_VALUES = {"none", "legacy_direct_cli", "fail_closed_until_prerequisite_ready", "fail_closed"}

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

    try:
        with open(default_path, "r") as f:
            default_content = f.read()
            
        try:
            default_config = json.loads(default_content)
        except json.JSONDecodeError as e:
            raise RegistryValidationError(f"engines.default.json is malformed: {e}\nRaw Content:\n{_redact_raw_json(default_content)}")

        _check_no_sensitive_keys(default_config, "engines.default.json")
        
        local_config = None
        if os.path.exists(local_path):
            if os.path.getsize(local_path) == 0:
                raise RegistryValidationError("engines.local.json is a zero-byte file")
            
            with open(local_path, "r") as f:
                local_content = f.read()
                
            try:
                local_config = json.loads(local_content)
            except json.JSONDecodeError as e:
                # Add the raw JSON into the exception to prove scrubbing works if it were exposed
                raise RegistryValidationError(f"engines.local.json is malformed: {e}\nRaw Content:\n{_redact_raw_json(local_content)}")

        merged_config = _merge_and_validate(default_config, local_config)
        return merged_config
    except RegistryValidationError:
        raise
    except Exception as e:
        error_msg = str(e)
        scrubbed_msg = _redact_raw_json(error_msg)
        raise RegistryValidationError(scrubbed_msg) from None


def build_spawner_engine_choices(registry):
    """Build CLI engine choices and alias-to-id mapping from a loaded registry.

    Returns (choices, alias_to_id, default_alias) tuple:
      - choices: list of user-facing aliases (cli_alias or engine_id) for argparse
      - alias_to_id: dict mapping alias → engine_id
      - default_alias: the alias for 'openclaw' or the first alias, always present in choices

    Callers should use default_alias as the argparse default so the default value
    is guaranteed to be in the choices list.
    """
    alias_to_id = {}
    for eid, entry in registry.get("engines", {}).items():
        if isinstance(entry, dict):
            alias = entry.get("cli_alias") or entry.get("engine_id", eid)
            alias_to_id[alias] = entry.get("engine_id", eid)
    choices = list(alias_to_id.keys()) or ["openclaw", "gemini"]
    # Resolve default_alias: find the alias that maps to 'openclaw_native',
    # or use the well-known literal 'openclaw' as a safe fallback.
    reverse_map = {eid: alias for alias, eid in alias_to_id.items()}
    default_alias = reverse_map.get("openclaw_native", "openclaw")
    if default_alias not in choices:
        default_alias = choices[0] if choices else "openclaw"
    return choices, alias_to_id, default_alias
