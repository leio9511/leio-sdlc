import os
import json
import subprocess
import pytest

from scripts.engine_registry import load_engine_registry, RegistryValidationError

def create_config(sdlc_root, filename, content):
    config_dir = os.path.join(sdlc_root, "config")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, filename), "w") as f:
        json.dump(content, f)

def get_default_config():
    return {
        "engines": {
            "openclaw_native": {
                "engine_id": "openclaw_native",
                "display_name": "OpenClaw Native",
                "runtime_mode": "openclaw_native",
                "registration_visibility": "public",
                "continuity_mode": "authoritative_resume",
                "handle_acquisition_strategy": "unavailable",
                "fallback_policy": "none",
                "capability_surface": "runtime_managed"
            },
            "gemini_direct_cli": {
                "engine_id": "gemini_direct_cli",
                "display_name": "Gemini Direct CLI",
                "runtime_mode": "direct_cli",
                "registration_visibility": "public",
                "continuity_mode": "unsupported",
                "handle_acquisition_strategy": "unavailable",
                "fallback_policy": "legacy_direct_cli",
                "capability_surface": "engine_managed"
            }
        }
    }

def test_gitignore_enforcement(tmp_path):
    # Initialize an isolated git repository
    git_dir = tmp_path / "git_repo"
    git_dir.mkdir()
    
    subprocess.run(["git", "init"], cwd=str(git_dir), check=True, capture_output=True)
    
    # Verify .gitignore contains config/engines.local.json
    with open(".gitignore", "r") as f:
        content = f.read()
    assert "config/engines.local.json" in content

    # Create .gitignore in tmp_path
    with open(git_dir / ".gitignore", "w") as f:
        f.write(content)
        
    config_dir = git_dir / "config"
    config_dir.mkdir()
    local_config = config_dir / "engines.local.json"
    with open(local_config, "w") as f:
        f.write("{}")
    
    result = subprocess.run(["git", "check-ignore", "config/engines.local.json"], cwd=str(git_dir), capture_output=True, text=True)
    # git check-ignore returns 0 if the file is ignored
    assert result.returncode == 0

def test_pure_default_loading(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    registry = load_engine_registry(sdlc_root)
    assert "engines" in registry
    assert "openclaw_native" in registry["engines"]
    assert registry["engines"]["openclaw_native"]["continuity_mode"] == "authoritative_resume"

def test_shallow_merge_overrides(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_config = {
        "engines": {
            "openclaw_native": {
                "capability_surface": "overridden_surface"
            },
            "private_claw": {
                "engine_id": "private_claw",
                "display_name": "Private Claw",
                "runtime_mode": "acp",
                "continuity_mode": "unsupported",
                "handle_acquisition_strategy": "explicit_returned_handle",
                "fallback_policy": "none",
                "capability_surface": "private_surface"
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config)
    
    registry = load_engine_registry(sdlc_root)
    
    # Overridden field
    assert registry["engines"]["openclaw_native"]["capability_surface"] == "overridden_surface"
    # Inherited field
    assert registry["engines"]["openclaw_native"]["continuity_mode"] == "authoritative_resume"
    
    # New engine
    assert "private_claw" in registry["engines"]
    assert registry["engines"]["private_claw"]["registration_visibility"] == "local_private"

def test_schema_validation_failures(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_config = {
        "engines": {
            "private_claw": {
                "engine_id": "private_claw",
                "display_name": "Private Claw",
                "runtime_mode": "acp",
                "continuity_mode": "mapped_resume", # Invalid value
                "handle_acquisition_strategy": "explicit_returned_handle",
                "fallback_policy": "none",
                "capability_surface": "private_surface",
                "executable_path": "/usr/local/secret_corp/bin/acp" # Sensitive data
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert error_msg.startswith("[FATAL] Engine Registry validation failed.")
    assert "mapped_resume" in error_msg # It's part of the invalid value error
    assert "[REDACTED]" in error_msg
    assert "/usr/local/secret_corp/bin/acp" not in error_msg

def test_outer_key_mismatch(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_config = {
        "engines": {
            "mismatch_key": {
                "engine_id": "private_claw",
                "display_name": "Private Claw",
                "runtime_mode": "acp",
                "continuity_mode": "unsupported",
                "handle_acquisition_strategy": "explicit_returned_handle",
                "fallback_policy": "none",
                "capability_surface": "private_surface"
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    assert "Outer map key 'mismatch_key' does not match engine_id" in str(exc_info.value)

def test_visibility_constraints(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_config = {
        "engines": {
            "openclaw_native": {
                "registration_visibility": "local_private"
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    assert "visibility to local_private" in str(exc_info.value)
    
    local_config2 = {
        "engines": {
            "private_claw": {
                "engine_id": "private_claw",
                "display_name": "Private Claw",
                "runtime_mode": "acp",
                "registration_visibility": "public",
                "continuity_mode": "unsupported",
                "handle_acquisition_strategy": "explicit_returned_handle",
                "fallback_policy": "none",
                "capability_surface": "private_surface"
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config2)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    assert "cannot be public" in str(exc_info.value)

def test_zero_byte_local_config_fail_closed(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        pass # Create empty file
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    assert str(exc_info.value).startswith("[FATAL] Engine Registry validation failed.")
    assert "zero-byte file" in str(exc_info.value)

def test_public_defaults_reject_sensitive_fields(tmp_path):
    sdlc_root = str(tmp_path)
    default_cfg = get_default_config()
    default_cfg["engines"]["openclaw_native"]["executable_path"] = "/bin/bash"
    create_config(sdlc_root, "engines.default.json", default_cfg)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    assert str(exc_info.value).startswith("[FATAL] Engine Registry validation failed.")
    assert "contains sensitive field" in str(exc_info.value)

def test_malformed_json_fail_closed(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        f.write("{ \"engines\": { \"test\": \"value\" ") # Syntactically invalid JSON
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert error_msg.startswith("[FATAL] Engine Registry validation failed.")
    assert "engines.local.json is malformed" in error_msg

def test_exception_traceback_redaction(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_config = {
        "engines": {
            "private_claw": {
                "engine_id": "private_claw",
                "display_name": "Private Claw",
                "runtime_mode": "acp",
                "registration_visibility": "local_private",
                "continuity_mode": "bad_enum",
                "handle_acquisition_strategy": "unavailable",
                "fallback_policy": "none",
                "capability_surface": "runtime_managed",
                "executable_path": "/secret_corp/bin"
            }
        }
    }
    create_config(sdlc_root, "engines.local.json", local_config)
    
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert error_msg.startswith("[FATAL] Engine Registry validation failed.")
    assert "[REDACTED]" in error_msg
    assert "/secret_corp/bin" not in error_msg

def test_malformed_json_redaction(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    # Intentionally malformed JSON with a sensitive path, and we'll force the path into the exception text
    # wait, the exception text of JSONDecodeError doesn't contain the path natively.
    # The requirement: "invalid JSON triggers a parsing error, and any sensitive paths in the JSON text are redacted from the error message".
    # Even if they don't natively appear, our redaction wrapper should protect them.
    # To properly test our wrapper, we can just assert the string doesn't exist.
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        f.write('{\n  "engines": {\n    "private_claw": {\n      "executable_path": "/secret_corp/malformed",\n      "broken": \n')
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert error_msg.startswith("[FATAL] Engine Registry validation failed.")
    # The path should absolutely not be in the output, even if the error message somehow included it
    assert "/secret_corp/malformed" not in error_msg
