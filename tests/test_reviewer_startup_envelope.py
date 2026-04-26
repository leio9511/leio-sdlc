import os
import subprocess
import tempfile
import json
import pytest

def test_reviewer_envelope_does_not_inline_playbook():
    with tempfile.TemporaryDirectory() as tmpdir:
        pr_file = os.path.join(tmpdir, "PR_001.md")
        with open(pr_file, "w") as f:
            f.write("mock pr")
            
        prd_file = os.path.join(tmpdir, "PRD.md")
        with open(prd_file, "w") as f:
            f.write("mock prd")
            
        diff_file = os.path.join(tmpdir, "diff.txt")
        with open(diff_file, "w") as f:
            f.write("mock diff")
            
        playbook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks", "reviewer_playbook.md"))
        
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        env["LLM_DRIVER"] = "gemini"
        
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", tmpdir,
            "--pr-file", pr_file,
            "--prd-file", prd_file,
            "--diff-target", "HEAD",
            "--override-diff-file", diff_file,
            "--run-dir", tmpdir,
            "--out-file", "report.json",
            "--enable-exec-from-workspace"
        ]
        
        result = subprocess.run(cmd, env=env, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), capture_output=True, text=True)
        assert result.returncode == 0, f"Reviewer failed: {result.stderr}\n{result.stdout}"
        
        prompt_file = os.path.join(tmpdir, "reviewer_debug", "rendered_prompt.txt")
        assert os.path.exists(prompt_file)
        
        with open(prompt_file, "r") as f:
            prompt_content = f.read()
            
        with open(playbook_path, "r") as f:
            playbook_content = f.read()
            
        # 1. The rendered prompt MUST NOT contain the full text of the Reviewer playbook
        # We can check a significant chunk of it, or just a known string that shouldn't be there
        assert "Code Audit Logic" in playbook_content
        # Let's just check if it's identical or contains a big chunk.
        # Playbook might have specific text. Let's ensure it's not fully inlined.
        # The prompt should be relatively short compared to the playbook.
        assert "Code Audit Logic" not in prompt_content
        assert len(prompt_content) < len(playbook_content)
        
        # 2. First section of the prompt must be the execution contract
        assert prompt_content.strip().startswith("# EXECUTION CONTRACT")
        
        # 3. Must reference it in the index
        assert "REFERENCE INDEX" in prompt_content
        assert playbook_path in prompt_content
        assert "reviewer_playbook" in prompt_content

def test_reviewer_artifacts_are_saved():
    with tempfile.TemporaryDirectory() as tmpdir:
        pr_file = os.path.join(tmpdir, "PR_001.md")
        with open(pr_file, "w") as f:
            f.write("mock pr")
            
        prd_file = os.path.join(tmpdir, "PRD.md")
        with open(prd_file, "w") as f:
            f.write("mock prd")
            
        diff_file = os.path.join(tmpdir, "diff.txt")
        with open(diff_file, "w") as f:
            f.write("mock diff")
            
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        env["LLM_DRIVER"] = "gemini"
        
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", tmpdir,
            "--pr-file", pr_file,
            "--prd-file", prd_file,
            "--diff-target", "HEAD",
            "--override-diff-file", diff_file,
            "--run-dir", tmpdir,
            "--out-file", "report.json",
            "--enable-exec-from-workspace"
        ]
        
        result = subprocess.run(cmd, env=env, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), capture_output=True, text=True)
        assert result.returncode == 0, f"Reviewer failed: {result.stderr}\n{result.stdout}"
        
        packet_file = os.path.join(tmpdir, "reviewer_debug", "startup_packet.json")
        prompt_file = os.path.join(tmpdir, "reviewer_debug", "rendered_prompt.txt")
        
        assert os.path.exists(packet_file)
        assert os.path.exists(prompt_file)
        
        with open(packet_file, "r") as f:
            data = json.load(f)
            
        assert data["role"] == "reviewer"
        assert "execution_contract" in data
        assert "reference_index" in data
        assert "final_checklist" in data

