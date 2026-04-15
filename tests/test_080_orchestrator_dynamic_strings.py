import os
import subprocess
import pytest
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))
import config

def test_orchestrator_dynamic_strings(tmp_path):
    os.chdir(tmp_path)
    subprocess.run(["git", "init"])
    
    # Make project compliant so we get past the doctor check
    doctor_script = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/doctor.py"
    subprocess.run(["python3", doctor_script, str(tmp_path), "--fix"])
    
    # Create uncommitted PRD file
    with open("PRD_uncommitted.md", "w") as f:
        f.write("uncommitted")

    orchestrator_script = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/scripts/orchestrator.py"
    
    env = os.environ.copy()
    custom_root = "/tmp/custom_skills_root"
    env["SDLC_SKILLS_ROOT"] = custom_root

    result = subprocess.run(
        ["python3", orchestrator_script, "--enable-exec-from-workspace", "--workdir", str(tmp_path), "--prd-file", "PRD_uncommitted.md", "--force-replan", "true"],
        capture_output=True,
        text=True,
        env=env
    )

    assert result.returncode == 1
    expected_error = f"[FATAL] Workspace contains uncommitted state files. You MUST baseline your PRD and state using the official gateway: python3 {custom_root}/leio-sdlc/scripts/commit_state.py --files <path>"
    assert expected_error in result.stdout
