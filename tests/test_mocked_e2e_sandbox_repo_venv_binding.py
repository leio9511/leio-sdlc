from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SANDBOX = REPO_ROOT / "scripts" / "e2e" / "setup_sandbox.sh"
DEV_PYTHON = REPO_ROOT / "scripts" / "dev_python.sh"


def _run_init_hermetic_sandbox(target_scripts_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            "-c",
            f"source {SETUP_SANDBOX}; init_hermetic_sandbox {target_scripts_dir}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_setup_sandbox_exposes_explicit_dev_python_entrypoint(tmp_path: Path):
    sandbox_scripts = tmp_path / "sandbox" / "scripts"

    result = _run_init_hermetic_sandbox(sandbox_scripts)

    assert result.returncode == 0, result.stdout + result.stderr
    sandbox_dev_python = sandbox_scripts / "dev_python.sh"
    assert sandbox_dev_python.is_file()
    assert os.access(sandbox_dev_python, os.X_OK)
    mode = sandbox_dev_python.stat().st_mode
    assert mode & stat.S_IXUSR


def test_sandbox_dev_python_entrypoint_points_to_repo_venv_contract(tmp_path: Path):
    sandbox_scripts = tmp_path / "sandbox" / "scripts"

    result = _run_init_hermetic_sandbox(sandbox_scripts)

    assert result.returncode == 0, result.stdout + result.stderr
    sandbox_dev_python = sandbox_scripts / "dev_python.sh"
    wrapper = sandbox_dev_python.read_text(encoding="utf-8")
    assert f'exec "{DEV_PYTHON}" "$@"' in wrapper
    assert "python3" not in wrapper
    assert "python " not in wrapper
    assert "pytest" not in wrapper
    assert "source .venv" not in wrapper
    assert ".venv/bin/activate" not in wrapper


def test_sandbox_setup_does_not_activate_or_mutate_trap_ambient_python(tmp_path: Path):
    sandbox_scripts = tmp_path / "sandbox" / "scripts"
    hostile_bin = tmp_path / "hostile_bin"
    hostile_bin.mkdir()
    trap_python = hostile_bin / "python3"
    trap_python.write_text(
        "#!/usr/bin/env bash\n"
        "echo trap ambient python must not be used by sandbox setup >&2\n"
        "exit 23\n",
        encoding="utf-8",
    )
    trap_python.chmod(trap_python.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{hostile_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"source {SETUP_SANDBOX}; init_hermetic_sandbox {sandbox_scripts}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "trap ambient python must not be used" not in result.stderr
    setup_source = SETUP_SANDBOX.read_text(encoding="utf-8")
    assert "source .venv" not in setup_source
    assert ".venv/bin/activate" not in setup_source
    assert "pip install" not in setup_source
