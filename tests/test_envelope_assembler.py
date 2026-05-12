import json
import pytest
from scripts.envelope_assembler import (
    build_startup_envelope,
    render_envelope_to_prompt,
    ROLE_PROLOGUES
)

ROLES = ["planner", "coder", "reviewer", "verifier", "auditor", "forensic"]

@pytest.fixture
def mock_params():
    return {
        "workdir": "/tmp/workdir",
        "out_dir": "/tmp/out_dir",
        "references": {
            "prd_file": "/tmp/prd.md",
            "playbook_path": "/tmp/playbook.md",
            "template_path": "/tmp/template.md",
            "diff_file": "/tmp/diff.patch",
            "pr_contract_file": "/tmp/pr.md",
            "prd_files": ["/tmp/prd1.md", "/tmp/prd2.md"],
        },
        "contract_params": {
            "scaffold_command": "scaffold.sh",
            "output_file": "/tmp/output.json",
            "output_schema": {"type": "object"}
        }
    }


def test_render_envelope_structure_and_sections(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        # If build_startup_envelope doesn't explicitly support forensic, it returns empty lists. We must manually set role.
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        assert "## IDENTITY & PRIMARY GOAL" in prompt
        # Wait, if a role has no constraints, we might not output OPERATING CONSTRAINTS in the current implementation.
        # But wait, forensic doesn't generate ANY constraints, so it won't have OPERATING CONSTRAINTS.
        # Let's check if the test requires it for ALL roles or if the implementation should just output it unconditionally.
        # "Asserts the presence of the exact section headers: IDENTITY, OPERATING CONSTRAINTS, START WORK"
        # I'll update the implementation to ALWAYS output the OPERATING CONSTRAINTS section.
        assert "## OPERATING CONSTRAINTS" in prompt, f"Missing OPERATING CONSTRAINTS for {role}"
        assert "## START WORK" in prompt


def test_render_envelope_preserves_execution_contract(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        for clause in envelope.get("execution_contract", []):
            assert clause in prompt, f"Missing clause in {role}: {clause}"


def test_render_envelope_preserves_references(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        expected_json = json.dumps(envelope.get("reference_index", []), indent=2)
        assert expected_json in prompt, f"Missing reference index for {role}"


def test_render_envelope_cta_last_section(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        sections = prompt.split("## ")
        last_section = "## " + sections[-1]
        
        assert last_section.startswith("## START WORK")
        assert f"As the {role.upper()}" in last_section


def test_render_envelope_role_prologues(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        expected_prologue = ROLE_PROLOGUES[role]
        assert expected_prologue in prompt
