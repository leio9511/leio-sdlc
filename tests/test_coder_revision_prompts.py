import pytest
import json
import os

def test_coder_revision_prompt_has_action_clauses():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    coder_revision = prompts.get("coder_revision", "")
    
    assert "This is an execution task, not an acknowledgment task." in coder_revision
    assert 'You MUST NOT respond with only an acknowledgment such as "I have read the instructions".' in coder_revision
    assert "If you do not make code changes after revision feedback, you have failed the task." in coder_revision
    assert "You MUST do all of the following in this turn:\n1. Extract the reviewer findings and identify the concrete files that must change.\n2. Modify the codebase to address every finding.\n3. Run the relevant tests and/or preflight until green.\n4. Commit the required files explicitly.\n5. Leave the workspace clean." in coder_revision

def test_coder_system_alert_has_action_clause():
    prompts_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json")
    with open(prompts_file, "r") as f:
        prompts = json.load(f)
    
    coder_system_alert = prompts.get("coder_system_alert", "")
    
    assert "This alert requires corrective action, not acknowledgment only." in coder_system_alert
