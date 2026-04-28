import json
import os
import tempfile

import pytest

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import spawn_coder
from envelope_assembler import save_envelope_artifacts


def test_rendered_coder_prompt_is_contract_first_and_path_driven():
    envelope, prompt = spawn_coder.build_coder_startup_packet_and_prompt(
        workdir="/tmp/workdir",
        run_dir="/tmp/run_dir",
        pr_file="/tmp/contracts/PR_001.md",
        prd_file="/tmp/docs/PRD.md",
        playbook_path="/tmp/playbooks/coder_playbook.md",
        mode="initial",
    )

    assert envelope["role"] == "coder"
    assert prompt.startswith("# EXECUTION CONTRACT")
    assert "/tmp/contracts/PR_001.md" in prompt
    assert "/tmp/docs/PRD.md" in prompt
    assert "/tmp/playbooks/coder_playbook.md" in prompt
    assert "--- PR Contract" not in prompt
    assert "--- PRD" not in prompt
    assert "--- CODER PLAYBOOK ---" not in prompt


def test_save_envelope_artifacts_supports_mode_scoped_paths():
    envelope = {
        "role": "coder",
        "execution_contract": ["clause"],
        "reference_index": [],
        "final_checklist": ["done"],
    }
    prompt = "# EXECUTION CONTRACT\n- clause"

    with tempfile.TemporaryDirectory() as tmpdir:
        debug_dir = save_envelope_artifacts(
            "coder",
            tmpdir,
            envelope,
            prompt,
            artifact_subdir="initial",
        )

        assert debug_dir == os.path.join(tmpdir, "coder_debug", "initial")
        packet_path = os.path.join(debug_dir, "startup_packet.json")
        prompt_path = os.path.join(debug_dir, "rendered_prompt.txt")
        assert os.path.exists(packet_path)
        assert os.path.exists(prompt_path)

        with open(packet_path, "r") as f:
            saved = json.load(f)
        assert saved["role"] == "coder"

        with open(prompt_path, "r") as f:
            saved_prompt = f.read()
        assert saved_prompt == prompt


def test_resolve_coder_artifact_subdir_numbers_repeated_modes():
    with tempfile.TemporaryDirectory() as tmpdir:
        assert spawn_coder.resolve_coder_artifact_subdir(tmpdir, "initial") == "initial"
        assert spawn_coder.resolve_coder_artifact_subdir(tmpdir, "revision") == "revision_001"

        os.makedirs(os.path.join(tmpdir, "coder_debug", "revision_001"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "coder_debug", "revision_002"), exist_ok=True)
        os.makedirs(os.path.join(tmpdir, "coder_debug", "system_alert_001"), exist_ok=True)

        assert spawn_coder.resolve_coder_artifact_subdir(tmpdir, "revision") == "revision_003"
        assert spawn_coder.resolve_coder_artifact_subdir(tmpdir, "system_alert") == "system_alert_002"
        assert spawn_coder.resolve_coder_artifact_subdir(tmpdir, "revision_bootstrap") == "revision_bootstrap_001"
