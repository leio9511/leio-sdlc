import pytest
import json
import os

def test_coder_revision_prompt_has_action_clauses():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    coder_revision = prompts.get("coder_revision", "")
    
    assert "__DEPRECATED__ use envelope_assembler.py" in coder_revision

def test_coder_system_alert_has_action_clause():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    coder_system_alert = prompts.get("coder_system_alert", "")
    
    assert "__DEPRECATED__ use envelope_assembler.py" in coder_system_alert
