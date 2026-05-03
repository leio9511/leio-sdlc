import sys
import subprocess
import pytest
from pathlib import Path
import os


def test_orchestrator_fail_fast_on_non_compliant_project(tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    os.system(f"git init {workdir}")
    # Run orchestrator, doctor should fail because no templates exist
    orch_script = Path(__file__).parent.parent / "scripts" / "orchestrator.py"

    # We will invoke orchestrator directly and check stderr/stdout
    res = subprocess.run([sys.executable, str(orch_script), "--workdir", str(workdir), "--prd-file", "PRD.md", "--channel", "test", "--force-replan", "false", "--enable-exec-from-workspace"], capture_output=True, text=True, env={**os.environ, "SDLC_TEST_MODE": "true"})

    assert res.returncode != 0
    assert "Project is not SDLC compliant" in res.stdout or "Project is not SDLC compliant" in res.stderr

    # TDD Test Case 6 (fail-fast counterpart): project with scaffold templates
    # but an outdated managed hook (schema version < 2) must also be blocked.
    workdir2 = tmp_path / "workdir2"
    workdir2.mkdir()
    os.system(f"git init {workdir2}")
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(workdir2), capture_output=True, text=True)
    doctor_script = Path(__file__).parent.parent / "scripts" / "doctor.py"
    # Apply scaffold via doctor --fix so template files are present
    res_fix = subprocess.run([sys.executable, str(doctor_script), str(workdir2), "--fix"], capture_output=True, text=True)
    assert res_fix.returncode == 0
    subprocess.run(["git", "add", "."], cwd=str(workdir2), capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "scaffold"], cwd=str(workdir2), capture_output=True, text=True)
    # Manually install an outdated managed hook (schema version 1)
    hook_path = workdir2 / ".git" / "hooks" / "pre-commit"
    hook_path.write_text("#!/bin/bash\n# SDLC_MANAGED_HOOK=leio-sdlc\n# SDLC_HOOK_SCHEMA_VERSION=1\n")
    os.chmod(hook_path, 0o755)
    # Verify doctor --check reports the outdated hook
    res_check = subprocess.run([sys.executable, str(doctor_script), str(workdir2), "--check"], capture_output=True, text=True)
    assert res_check.returncode == 1
    assert "Managed hook requires upgrade" in res_check.stdout
    # Orchestrator should block on this project because the managed hook is outdated
    res2 = subprocess.run([sys.executable, str(orch_script), "--workdir", str(workdir2), "--prd-file", "PRD.md", "--channel", "test", "--force-replan", "false", "--enable-exec-from-workspace"], capture_output=True, text=True, env={**os.environ, "SDLC_TEST_MODE": "true"})
    assert res2.returncode != 0
    assert "Project is not SDLC compliant" in res2.stdout or "Project is not SDLC compliant" in res2.stderr


def test_orchestrator_proceeds_on_compliant_project(tmp_path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    os.system(f"git init {workdir}")
    
    # Needs a baseline commit or git init will complain about branches
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(workdir))
    
    # Need to manually create the mock template directory inside the skill, but we use the real one for orchestrator test
    # The real templates exist because of PR-001
    
    doctor_script = Path(__file__).parent.parent / "scripts" / "doctor.py"
    res1 = subprocess.run([sys.executable, str(doctor_script), str(workdir), "--fix"], capture_output=True, text=True)
    assert res1.returncode == 0
    
    # We must explicitly stage and commit the scaffold files created by doctor
    subprocess.run(["git", "add", "."], cwd=str(workdir))
    subprocess.run(["git", "commit", "-m", "scaffold"], cwd=str(workdir))
    
    # We also need to touch PRD.md to avoid "validate_prd_is_committed" crash
    # Oh wait, orchestrator.py will crash because PRD.md is missing. Let's see if the doctor check happens before.
    # Ah, doctor check is right at the top! So PRD check comes later.
    # But wait, doctor.py check runs apply_overlay with check_only.
    # Let's verify what doctor.py check returns for workdir.
    
    res2 = subprocess.run([sys.executable, str(doctor_script), str(workdir), "--check"], capture_output=True, text=True)
    print("Doctor check output:", res2.stdout)
    assert res2.returncode == 0

    # TDD Test Case 6 (compliant path): verify the managed hook installed by doctor
    # has the current managed metadata header and schema version 2.
    managed_hook_path = workdir / ".git" / "hooks" / "pre-commit"
    assert managed_hook_path.exists()
    assert os.access(managed_hook_path, os.X_OK)
    with open(managed_hook_path, "r") as f:
        hook_content = f.read()
    assert "# SDLC_MANAGED_HOOK=leio-sdlc" in hook_content
    assert "# SDLC_HOOK_SCHEMA_VERSION=2" in hook_content

    orch_script = Path(__file__).parent.parent / "scripts" / "orchestrator.py"
    res = subprocess.run([sys.executable, str(orch_script), "--workdir", str(workdir), "--prd-file", "PRD.md", "--channel", "test", "--force-replan", "false", "--enable-exec-from-workspace", "--test-sleep"], capture_output=True, text=True, env={**os.environ, "SDLC_TEST_MODE": "true"})

    # Should not print the compliant error
    assert "Project is not SDLC compliant" not in res.stdout
    assert "Project is not SDLC compliant" not in res.stderr
