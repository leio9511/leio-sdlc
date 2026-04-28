import pytest
import json
import os

def test_coder_prompt_entries_are_deprecated_markers():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    assert prompts.get("coder", "") == "__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py"
    assert prompts.get("coder_revision", "") == "__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py"
    assert prompts.get("coder_system_alert", "") == "__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py"

def test_coder_prompt_entries_no_longer_contain_active_startup_prose():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    coder = prompts.get("coder", "")
    coder_revision = prompts.get("coder_revision", "")
    coder_system_alert = prompts.get("coder_system_alert", "")
    
    assert "playbook" not in coder.lower()
    assert "revision" not in coder_revision.lower() or "__DEPRECATED__" in coder_revision
    assert "alert" not in coder_system_alert.lower() or "__DEPRECATED__" in coder_system_alert

