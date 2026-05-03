import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.doctor import _read_managed_hook_schema_version

DOCTOR_SCRIPT = Path(__file__).parents[1] / "scripts" / "doctor.py"


def test_doctor_check_flags_missing_managed_hook_metadata(tmp_path):
    """A hook without the managed header/schema metadata is reported non-compliant."""
    subprocess.run(
        ["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True
    )
    hook_dir = tmp_path / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    # Hook with NO managed metadata at all — bare legacy hook
    hook_path.write_text("#!/bin/bash\necho 'legacy hook'\n")
    os.chmod(hook_path, 0o755)

    result = subprocess.run(
        [sys.executable, str(DOCTOR_SCRIPT), str(tmp_path), "--check"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Managed hook requires upgrade" in result.stdout


def test_doctor_check_flags_outdated_hook_schema_version(tmp_path):
    """An installed managed hook with schema version lower than 2 is reported as requiring upgrade."""
    subprocess.run(
        ["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True
    )
    hook_dir = tmp_path / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    # Hook with managed metadata but schema version 1
    hook_path.write_text(
        "#!/bin/bash\n# SDLC_MANAGED_HOOK=leio-sdlc\n# SDLC_HOOK_SCHEMA_VERSION=1\nexit 0\n"
    )
    os.chmod(hook_path, 0o755)

    result = subprocess.run(
        [sys.executable, str(DOCTOR_SCRIPT), str(tmp_path), "--check"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Managed hook requires upgrade" in result.stdout


def test_doctor_fix_replaces_outdated_hook_with_current_managed_version(tmp_path):
    """doctor.py --fix overwrites the outdated hook, installs the current managed header, and leaves the hook executable."""
    subprocess.run(
        ["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True
    )
    hook_dir = tmp_path / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    # Outdated hook with schema version 1
    hook_path.write_text(
        "#!/bin/bash\n# SDLC_MANAGED_HOOK=leio-sdlc\n# SDLC_HOOK_SCHEMA_VERSION=1\nexit 0\n"
    )
    os.chmod(hook_path, 0o755)

    # --enforce-git-lock is required to trigger the managed hook installation into
    # .git/hooks/; --fix alone handles scaffold/overlay compliance only.
    res = subprocess.run(
        [
            sys.executable,
            str(DOCTOR_SCRIPT),
            str(tmp_path),
            "--fix",
            "--enforce-git-lock",
        ],
        capture_output=True,
        text=True,
    )

    assert res.returncode == 0
    # Hook should now have current schema version
    assert _read_managed_hook_schema_version(hook_path) == "2"
    # Hook should be executable
    assert os.access(hook_path, os.X_OK)
    # Hook should contain managed metadata header
    with open(hook_path, "r") as f:
        content = f.read()
    assert "# SDLC_MANAGED_HOOK=leio-sdlc" in content
