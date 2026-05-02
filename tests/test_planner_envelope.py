import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from planner_envelope import build_planner_envelope, render_planner_prompt


def test_slice_failed_pr_envelope_includes_failed_pr_contract_reference():
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd.md",
        playbook_path="/mock/playbook.md",
        template_path="/mock/template.md",
        contract_script="/mock/contract_script.py",
        mode="slice",
        failed_pr_id="002",
        failed_pr_contract_path="/mock/PR_002_failed.md",
    )

    refs_by_id = {ref["id"]: ref for ref in envelope["reference_index"]}
    assert refs_by_id["failed_pr_contract"] == {
        "id": "failed_pr_contract",
        "kind": "pr_contract",
        "path": "/mock/PR_002_failed.md",
        "required": True,
        "priority": 1,
        "purpose": "failed_slice_boundary_source",
    }


def test_slice_failed_pr_rendered_prompt_contains_failed_contract_reference_and_insert_after():
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd.md",
        playbook_path="/mock/playbook.md",
        template_path="/mock/template.md",
        contract_script="/mock/contract_script.py",
        mode="slice",
        failed_pr_id="002",
        failed_pr_contract_path="/mock/PR_002_failed.md",
    )

    prompt = render_planner_prompt(envelope)

    assert "failed_pr_contract" in prompt
    assert "/mock/PR_002_failed.md" in prompt
    assert "You MUST use the exact same `--insert-after 002` value" in prompt


def test_standard_and_uat_planner_envelopes_do_not_include_failed_pr_contract():
    standard_envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd.md",
        playbook_path="/mock/playbook.md",
        template_path="/mock/template.md",
        contract_script="/mock/contract_script.py",
        failed_pr_contract_path="/mock/PR_002_failed.md",
    )
    uat_envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd.md",
        playbook_path="/mock/playbook.md",
        template_path="/mock/template.md",
        contract_script="/mock/contract_script.py",
        mode="uat",
        uat_report_path="/mock/uat.json",
        failed_pr_contract_path="/mock/PR_002_failed.md",
    )

    for envelope in (standard_envelope, uat_envelope):
        ref_ids = {ref["id"] for ref in envelope["reference_index"]}
        assert "failed_pr_contract" not in ref_ids


def test_envelope_top_level_keys():
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd",
        playbook_path="/mock/playbook",
        template_path="/mock/template",
        contract_script="/mock/contract_script.py"
    )
    keys = set(envelope.keys())
    assert keys == {"execution_contract", "reference_index", "final_checklist", "role"}
    assert "task_brief" not in keys

def test_envelope_reference_index_contents():
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd.md",
        playbook_path="/mock/playbook.md",
        template_path="/mock/template.md",
        contract_script="/mock/contract_script.py"
    )
    ref_index = envelope["reference_index"]
    assert len(ref_index) == 3
    
    # Authoritative PRD
    assert ref_index[0]["id"] == "authoritative_prd"
    assert ref_index[0]["path"] == "/mock/prd.md"
    assert ref_index[0]["required"] is True
    assert ref_index[0]["priority"] == 1
    
    # Planner Playbook
    assert ref_index[1]["id"] == "planner_playbook"
    assert ref_index[1]["path"] == "/mock/playbook.md"
    assert ref_index[1]["required"] is True
    assert ref_index[1]["priority"] == 1
    
    # Template
    assert ref_index[2]["id"] == "pr_contract_template"
    assert ref_index[2]["path"] == "/mock/template.md"
    assert ref_index[2]["required"] is True
    assert ref_index[2]["priority"] == 1

def test_rendered_prompt_sections():
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd",
        playbook_path="/mock/playbook",
        template_path="/mock/template",
        contract_script="/mock/contract_script.py"
    )
    prompt = render_planner_prompt(envelope)
    
    assert "# EXECUTION CONTRACT" in prompt
    assert "# REFERENCE INDEX" in prompt
    assert "# FINAL CHECKLIST" in prompt

def test_rendered_prompt_no_inlining():
    # We want to ensure that the actual text body of the PRD is NOT inlined.
    # The reference index contains the *path*, not the *content*. 
    # By passing specific paths, we verify the paths are present, but obviously 
    # there is no place where we pass full document content into the envelope builder.
    # The rendered prompt should be short and structured.
    
    envelope = build_planner_envelope(
        workdir="/mock/workdir",
        out_dir="/mock/out_dir",
        prd_path="/mock/prd_path.md",
        playbook_path="/mock/playbook_path.md",
        template_path="/mock/template_path.md",
        contract_script="/mock/contract_script.py"
    )
    prompt = render_planner_prompt(envelope)
    
    # Verify the paths are present in the prompt (within JSON)
    assert "/mock/prd_path.md" in prompt
    assert "/mock/playbook_path.md" in prompt
    
    # But prove that no large text blocks exist - basically proving progressive disclosure.
    # The prompt shouldn't contain large arbitrary markdown text from those files
    # because the `render_planner_prompt` only renders the envelope JSON/dict.
    assert "authoritative_requirements" in prompt
    assert prompt.count("#") == 3 # only our section headers should be present (no PRD headers)
