import os
import json
from scripts.planner_envelope import render_planner_prompt

def test_envelope_supports_auditor():
    envelope = {
        "execution_contract": [
            "Read-only behavior required. Do not modify files.",
            "Output must be a structured JSON report."
        ],
        "reference_index": [
            {
                "id": "authoritative_prd",
                "kind": "prd",
                "path": "/some/path/prd.md",
                "required": True,
                "priority": 1,
                "purpose": "authoritative_requirements"
            },
            {
                "id": "auditor_playbook",
                "kind": "playbook",
                "path": "/some/path/auditor_playbook.md",
                "required": True,
                "priority": 1,
                "purpose": "auditor_methodology"
            }
        ],
        "final_checklist": [
            "Validate PRD completeness.",
            "Verify no files were modified."
        ]
    }
    
    prompt = render_planner_prompt(envelope)
    
    assert "# EXECUTION CONTRACT" in prompt
    assert "Read-only behavior required." in prompt
    assert "# REFERENCE INDEX" in prompt
    assert "auditor_playbook" in prompt
    assert "# FINAL CHECKLIST" in prompt
    assert "Validate PRD completeness." in prompt


def test_envelope_supports_reviewer():
    envelope = {
        "execution_contract": [
            "Review the provided PR diff.",
            "If issues found, raise system alert for recovery."
        ],
        "reference_index": [
            {
                "id": "pr_diff",
                "kind": "diff",
                "path": "/some/path/pr.diff",
                "required": True,
                "priority": 1,
                "purpose": "changes_to_review"
            },
            {
                "id": "pr_contract",
                "kind": "contract",
                "path": "/some/path/PR_001.md",
                "required": True,
                "priority": 1,
                "purpose": "expected_functionality"
            }
        ],
        "final_checklist": [
            "Ensure code meets PR contract.",
            "Verify all tests pass."
        ]
    }
    
    prompt = render_planner_prompt(envelope)
    
    assert "# EXECUTION CONTRACT" in prompt
    assert "Review the provided PR diff." in prompt
    assert "# REFERENCE INDEX" in prompt
    assert "pr_diff" in prompt
    assert "diff" in prompt
    assert "# FINAL CHECKLIST" in prompt
    assert "Verify all tests pass." in prompt


def test_envelope_supports_verifier():
    envelope = {
        "execution_contract": [
            "Verify the codebase state matches the PRD/UAT target."
        ],
        "reference_index": [
            {
                "id": "codebase_snapshot",
                "kind": "codebase",
                "path": "/some/path/snapshot",
                "required": True,
                "priority": 1,
                "purpose": "verification_target"
            }
        ],
        "final_checklist": [
            "Ensure actual behavior matches documented behavior."
        ]
    }
    
    prompt = render_planner_prompt(envelope)
    
    assert "# EXECUTION CONTRACT" in prompt
    assert "Verify the codebase state matches" in prompt
    assert "# REFERENCE INDEX" in prompt
    assert "codebase_snapshot" in prompt
    assert "# FINAL CHECKLIST" in prompt
    assert "Ensure actual behavior matches" in prompt


def test_envelope_supports_coder():
    envelope = {
        "execution_contract": [
            "Implement feature described in PR contract.",
            "Maintain persistent session and iterate on revision loops."
        ],
        "reference_index": [
            {
                "id": "pr_contract",
                "kind": "contract",
                "path": "/some/path/PR_001.md",
                "required": True,
                "priority": 1,
                "purpose": "task_specification"
            },
            {
                "id": "coder_playbook",
                "kind": "playbook",
                "path": "/some/path/coder_playbook.md",
                "required": True,
                "priority": 1,
                "purpose": "coder_methodology"
            }
        ],
        "final_checklist": [
            "Code is fully implemented.",
            "Tests are written and passing."
        ]
    }
    
    prompt = render_planner_prompt(envelope)
    
    assert "# EXECUTION CONTRACT" in prompt
    assert "Implement feature described" in prompt
    assert "# REFERENCE INDEX" in prompt
    assert "coder_playbook" in prompt
    assert "# FINAL CHECKLIST" in prompt
    assert "Tests are written and passing." in prompt


def test_playbook_is_methodology_only():
    # Read the planner playbook and ensure it does not contain rigid output constraints or script flags
    playbook_path = "/root/projects/leio-sdlc/playbooks/planner_playbook.md"
    with open(playbook_path, "r") as f:
        playbook_content = f.read()

    # The playbook should no longer mention --only-scaffold
    assert "--only-scaffold" not in playbook_content

    # The playbook should not have rigid output directory mandates like out_dir or .sdlc_runs in its body
    assert "out_dir" not in playbook_content
    assert ".sdlc_runs" not in playbook_content
    
    # Check that it defers to execution contract (which we just added)
    assert "following the execution contract instructions" in playbook_content
