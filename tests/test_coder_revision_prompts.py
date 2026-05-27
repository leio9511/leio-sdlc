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


def test_stateless_retry_prompt_contains_previous_stdout_and_feedback():
    """TC3: In stateless retry scenario, rendered prompt contains both previous
    coder stdout (via CODER_RETRY_PREVIOUS_OUTPUT_HEADER) and reviewer feedback."""
    import sys
    import tempfile
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
    import envelope_assembler

    sample_stdout = "previous agent output: test passed"
    with tempfile.TemporaryDirectory() as tmp_dir:
        fb_path = os.path.join(tmp_dir, "feedback.json")
        with open(fb_path, "w") as f:
            f.write('{"overall_assessment": "NEEDS_ATTENTION"}')
        for ref in ["prd.md", "pr.md", "playbook.md"]:
            with open(os.path.join(tmp_dir, ref), "w") as f:
                f.write("placeholder")
        references = {
            "prd_file": os.path.join(tmp_dir, "prd.md"),
            "pr_contract_file": os.path.join(tmp_dir, "pr.md"),
            "playbook_path": os.path.join(tmp_dir, "playbook.md"),
            "feedback_file": fb_path,
        }

        envelope = envelope_assembler.build_startup_envelope(
            role="coder",
            workdir=tmp_dir,
            out_dir=tmp_dir,
            references=references,
            contract_params={"previous_output": sample_stdout},
            mode="revision_bootstrap",
        )
        prompt = envelope_assembler.render_envelope_to_prompt(envelope)

        assert "## PREVIOUS CODER OUTPUT" in prompt
        assert sample_stdout in prompt
        assert "feedback.json" in prompt
        assert "prd.md" in prompt
        assert "pr.md" in prompt
