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
                "cli_alias": "openclaw",
                "display_name": "OpenClaw Native",
                "runtime_mode": "openclaw_native",
                "registration_visibility": "public",
                "continuity_mode": "stateful",
                "handle_acquisition_strategy": "unavailable",
                "fallback_policy": "none",
                "capability_surface": "runtime_managed"
            },
            "gemini_direct_cli": {
                "engine_id": "gemini_direct_cli",
                "cli_alias": "gemini",
                "display_name": "Gemini Direct CLI",
                "runtime_mode": "direct_cli",
                "registration_visibility": "public",
                "continuity_mode": "stateless",
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
    assert registry["engines"]["openclaw_native"]["continuity_mode"] == "stateful"

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
                "continuity_mode": "stateless",
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
    assert registry["engines"]["openclaw_native"]["continuity_mode"] == "stateful"
    
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
                "continuity_mode": "stateless",
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
                "continuity_mode": "stateless",
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
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        f.write('{\n  "engines": {\n    "private_claw": {\n      "executable_path": "/secret_corp/malformed\n    }\n  }\n}')
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert error_msg.startswith("[FATAL] Engine Registry validation failed.")
    assert "/secret_corp/malformed" not in error_msg
    assert "[REDACTED]" in error_msg

def test_malformed_json_escaped_quotes(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        f.write('{\n  "engines": {\n    "private_claw": {\n      "executable_path": "/secret_corp/\\"escaped\\"",\n      "broken": \n')
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert "/secret_corp/\\\"escaped\\\"" not in error_msg
    assert "[REDACTED]" in error_msg


def test_continuity_mode_accepts_only_stateful_or_stateless(tmp_path):
    sdlc_root = str(tmp_path)
    for valid_mode in ("stateful", "stateless"):
        cfg = get_default_config()
        cfg["engines"]["openclaw_native"]["continuity_mode"] = valid_mode
        create_config(sdlc_root, "engines.default.json", cfg)
        registry = load_engine_registry(sdlc_root)
        assert registry["engines"]["openclaw_native"]["continuity_mode"] == valid_mode

    for legacy_mode in ("mapped_resume", "degraded_resume", "authoritative_resume", "unsupported"):
        cfg = get_default_config()
        cfg["engines"]["openclaw_native"]["continuity_mode"] = legacy_mode
        create_config(sdlc_root, "engines.default.json", cfg)
        with pytest.raises(RegistryValidationError) as exc_info:
            load_engine_registry(sdlc_root)
        assert str(exc_info.value).startswith("[FATAL] Engine Registry validation failed.")
        assert legacy_mode in str(exc_info.value)


def test_default_engine_registry_uses_new_continuity_modes():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    registry = load_engine_registry(repo_root)
    legacy_modes = {"mapped_resume", "degraded_resume", "authoritative_resume", "unsupported"}
    modes = {entry["continuity_mode"] for entry in registry["engines"].values()}
    assert modes <= {"stateful", "stateless"}
    assert not modes & legacy_modes


def test_fallback_policy_accepts_fail_closed(tmp_path):
    sdlc_root = str(tmp_path)
    cfg = get_default_config()
    cfg["engines"]["gemini_direct_cli"]["fallback_policy"] = "fail_closed"
    create_config(sdlc_root, "engines.default.json", cfg)
    registry = load_engine_registry(sdlc_root)
    assert registry["engines"]["gemini_direct_cli"]["fallback_policy"] == "fail_closed"


def test_agy_direct_cli_default_entry_validates():
    """TC1: default registry loads agy_direct_cli with runtime_mode=direct_cli,
    continuity_mode=stateless, fallback_policy=fail_closed, and cli_alias=agy."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    registry = load_engine_registry(repo_root)
    engines = registry["engines"]
    assert "agy_direct_cli" in engines
    agy = engines["agy_direct_cli"]
    assert agy["runtime_mode"] == "direct_cli"
    assert agy["continuity_mode"] == "stateless"
    assert agy["fallback_policy"] == "fail_closed"
    assert agy["cli_alias"] == "agy"
    assert agy["capability_surface"] == "client_mediated"
    assert agy["execution"]["timeout_seconds"] == 3600
    assert agy["execution"]["env_extra"]["print-timeout"] == "3600s"
    assert "--print-timeout" not in agy["execution"]["one_shot_args"]
    assert "3600s" not in agy["execution"]["one_shot_args"]


def test_future_direct_cli_fixture_validates_as_stateless(tmp_path):
    """PR-006 TC4: A synthetic direct CLI engine with cli_alias,
    runtime_mode=direct_cli, continuity_mode=stateless,
    fallback_policy=fail_closed, and a minimal valid execution subsection
    validates and resolves without code changes."""
    sdlc_root = str(tmp_path)
    cfg = get_default_config()
    cfg["engines"]["future_direct_cli"] = {
        "engine_id": "future_direct_cli",
        "cli_alias": "future-cli",
        "display_name": "Future Direct CLI Engine",
        "runtime_mode": "direct_cli",
        "registration_visibility": "public",
        "continuity_mode": "stateless",
        "handle_acquisition_strategy": "unavailable",
        "fallback_policy": "fail_closed",
        "capability_surface": "client_mediated",
        "execution": {
            "executable": "future-cli",
            "one_shot_args": ["--generate"],
            "model_arg": None,
            "workspace_arg": None,
            "permission_args": [],
            "sandbox_args": [],
            "timeout_seconds": 120,
            "env_extra": {}
        }
    }
    create_config(sdlc_root, "engines.default.json", cfg)

    registry = load_engine_registry(sdlc_root)
    assert "future_direct_cli" in registry["engines"]
    future = registry["engines"]["future_direct_cli"]
    assert future["runtime_mode"] == "direct_cli"
    assert future["continuity_mode"] == "stateless"
    assert future["fallback_policy"] == "fail_closed"
    assert future["cli_alias"] == "future-cli"
    assert future["capability_surface"] == "client_mediated"

    # Verify alias resolution works from the registry
    from scripts.engine_registry import build_spawner_engine_choices
    choices, alias_to_id, default_alias = build_spawner_engine_choices(registry)
    assert "future-cli" in choices
    assert alias_to_id["future-cli"] == "future_direct_cli"


def test_malformed_json_unquoted(tmp_path):
    sdlc_root = str(tmp_path)
    create_config(sdlc_root, "engines.default.json", get_default_config())
    
    local_path = os.path.join(sdlc_root, "config", "engines.local.json")
    with open(local_path, "w") as f:
        f.write('{\n  "engines": {\n    "private_claw": {\n      "executable_path": /secret_corp/unquoted,\n      "broken": \n')
        
    with pytest.raises(RegistryValidationError) as exc_info:
        load_engine_registry(sdlc_root)
        
    error_msg = str(exc_info.value)
    assert "/secret_corp/unquoted" not in error_msg
    assert "[REDACTED]" in error_msg
