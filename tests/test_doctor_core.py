import os
import tempfile
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.doctor import check_vcs, apply_overlay, _read_managed_hook_schema_version

import pytest
def test_doctor_append_logic_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        overlay = Path(tmpdir) / "overlay"
        overlay.mkdir()
        
        append_file = overlay / "test.txt.append"
        with open(append_file, "w") as f:
            f.write("line1\nline2\n")
            
        target = Path(tmpdir) / "target"
        target.mkdir()
        
        # First apply
        apply_overlay(target, overlay, check_only=False)
        dest_file = target / "test.txt"
        with open(dest_file, "r") as f:
            content = f.read()
        assert "line1\nline2\n" == content
        
        # Second apply
        apply_overlay(target, overlay, check_only=False)
        with open(dest_file, "r") as f:
            content2 = f.read()
        assert "line1\nline2\n" == content2

def test_doctor_check_vcs_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        check_vcs(tmpdir)
        assert os.path.exists(os.path.join(tmpdir, ".git"))
        
        # Check if there is a baseline commit
        out = subprocess.run(["git", "log", "--oneline"], cwd=tmpdir, capture_output=True, text=True)
        assert "Baseline commit" in out.stdout

def test_doctor_apply_base_scaffold():
    with tempfile.TemporaryDirectory() as tmpdir:
        overlay = Path(tmpdir) / "overlay"
        overlay.mkdir(parents=True)
        with open(overlay / "STATE.md", "w") as f:
            f.write("# STATE")
        with open(overlay / "preflight.sh", "w") as f:
            f.write("echo 'ok'")
        with open(overlay / ".gitignore.append", "w") as f:
            f.write(".sdlc_runs/")
            
        target = Path(tmpdir) / "target"
        target.mkdir()
        
        apply_overlay(target, overlay, check_only=False)
        
        assert (target / "STATE.md").exists()
        assert (target / "preflight.sh").exists()
        assert (target / ".gitignore").exists()
        
        with open(target / ".gitignore", "r") as f:
            assert ".sdlc_runs/" in f.read()

def test_doctor_check_reports_runtime_aware_fix_path(tmp_path):
    custom_root = "/tmp/custom_skills_root"
    env = os.environ.copy()
    env["SDLC_RUNTIME_DIR"] = custom_root

    # TDD Test Case 4: set up a git repo with an outdated managed hook so that
    # both the runtime-aware JIT fix path AND the outdated-hook upgrade message coexist.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    hook_dir = tmp_path / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    hook_path.write_text("#!/bin/bash\n# SDLC_MANAGED_HOOK=leio-sdlc\n# SDLC_HOOK_SCHEMA_VERSION=1\n")
    os.chmod(hook_path, 0o755)

    script = Path(__file__).parent.parent / "scripts" / "doctor.py"

    result = subprocess.run(
        ["python3", str(script), str(tmp_path), "--check"],
        capture_output=True, text=True, env=env
    )
    assert result.returncode == 1
    # Runtime-aware JIT fix path remains correct
    assert f"[JIT] To fix: Execute `python3 {custom_root}/leio-sdlc/scripts/doctor.py --fix" in result.stdout
    # Outdated-hook detection coexists with the JIT hint
    assert "Managed hook requires upgrade: .git/hooks/pre-commit" in result.stdout


def test_doctor_detects_outdated_managed_hook(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    hook_dir = tmp_path / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    hook_path.write_text("#!/bin/bash\n# SDLC_MANAGED_HOOK=leio-sdlc\n")

    script = Path(__file__).parent.parent / "scripts" / "doctor.py"
    result = subprocess.run(
        ["python3", str(script), str(tmp_path), "--check"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Managed hook requires upgrade: .git/hooks/pre-commit" in result.stdout
