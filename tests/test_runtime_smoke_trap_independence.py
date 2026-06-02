import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
PREFLIGHT = REPO_ROOT / "preflight.sh"
RUNTIME_SMOKE = SCRIPTS_DIR / "runtime_smoke.py"
RUNTIME_PYTHON_WRAPPER = SCRIPTS_DIR / "runtime_python.sh"
TRAP_ENV_MARKERS = (
    "TRAP_VENV_DIR",
    "PREFLIGHT_TRAP_VENV_MARKER_FILE",
    "PREFLIGHT_BASE_PATH",
    "PREFLIGHT_BASE_VIRTUAL_ENV",
    "activate_trap_mode",
    "enter_trap_ambient",
    "leave_trap_ambient",
)


def _copy_minimal_skill_root(target_root):
    scripts_dir = target_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for name in (
        "runtime_smoke.py",
        "runtime_launch_guard.py",
        "runtime_python.sh",
        "config.py",
        "engine_registry.py",
        "utils_json.py",
    ):
        shutil.copy2(SCRIPTS_DIR / name, scripts_dir / name)
    (scripts_dir / "runtime_python.sh").chmod(0o755)
    shutil.copy2(REQUIREMENTS, target_root / "requirements.txt")
    return scripts_dir / "runtime_smoke.py"


def _create_runtime_venv(skill_root):
    venv_dir = skill_root / ".venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    
    # Symlink python to the active python running tests
    runtime_python = bin_dir / "python"
    if not runtime_python.exists():
        runtime_python.symlink_to(sys.executable)
        
    # Write pyvenv.cfg to activate virtual environment path resolution
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    pyvenv_cfg.write_text(
        f"home = {os.path.dirname(sys.executable)}\n"
        "include-system-site-packages = false\n"
        f"version = {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\n",
        encoding="utf-8"
    )
    
    # Symlink lib to parent venv's lib folder so we inherit all installed dependencies
    parent_venv = REPO_ROOT / ".venv"
    parent_lib = parent_venv / "lib"
    mock_lib = venv_dir / "lib"
    if parent_lib.exists() and not mock_lib.exists():
        mock_lib.symlink_to(parent_lib)
        
    return runtime_python


def _run_smoke(python, smoke_path, *args, cwd=None, env=None):
    return subprocess.run(
        [str(python), str(smoke_path), *map(str, args)],
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _run_runtime_wrapper(skill_root):
    return subprocess.run(
        [
            "bash",
            str(skill_root / "scripts" / "runtime_python.sh"),
            str(skill_root / "scripts" / "runtime_smoke.py"),
        ],
        cwd=str(skill_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _make_executable(path):
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_text(path, content, *, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        _make_executable(path)


def _copy_minimal_preflight_fixture(target_root):
    target_root.mkdir(parents=True)
    preflight_path = target_root / "preflight.sh"
    shutil.copy2(PREFLIGHT, preflight_path)
    _make_executable(preflight_path)
    _write_text(target_root / "ignore_tests.json", '{"bash": [], "pytest": []}\n')
    _write_text(
        target_root / "scripts" / "dev_python.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {sys.executable} \"$@\"\n",
        executable=True,
    )
    _write_text(
        target_root / "TEMPLATES" / "placeholder.md.template",
        "---\nstatus: pending\n---\n",
    )
    _write_text(
        target_root / "scripts" / "structured_state_parser.py",
        "from pathlib import Path\n\n"
        "VALID_STATES = {'pending', 'in_progress', 'completed'}\n\n"
        "def get_status(path):\n"
        "    text = Path(path).read_text(encoding='utf-8')\n"
        "    for line in text.splitlines():\n"
        "        if line.startswith('status:'):\n"
        "            return line.split(':', 1)[1].strip()\n"
        "    return None\n",
    )
    _write_text(
        target_root / "tests" / "test_template_compliance.py",
        (REPO_ROOT / "tests" / "test_template_compliance.py").read_text(encoding="utf-8"),
    )
    _write_text(
        target_root / "tests" / "test_allowed.py",
        "def test_allowed_placeholder():\n"
        "    assert True\n",
    )
    return preflight_path


def test_runtime_smoke_rejects_trap_or_ambient_python_when_runtime_venv_expected(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    trap_root = tmp_path / "trap-ambient"
    smoke_path = _copy_minimal_skill_root(skill_root)
    trap_python = _create_runtime_venv(trap_root)
    expected_runtime_python = skill_root / ".venv" / "bin" / "python"

    result = _run_smoke(
        trap_python,
        smoke_path,
        "--skill-root",
        skill_root,
        cwd=skill_root,
    )

    assert result.returncode != 0
    assert "Runtime Python interpreter mismatch" in result.stderr
    assert f"expected={os.path.realpath(expected_runtime_python)}" in result.stderr
    assert f"expected_identity={expected_runtime_python}" in result.stderr
    assert f"actual={os.path.realpath(trap_python)}" in result.stderr
    assert f"actual_identity={trap_python}" in result.stderr


def test_runtime_smoke_rejects_host_python_when_runtime_venv_expected(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _create_runtime_venv(skill_root)

    result = _run_smoke(sys.executable, smoke_path, "--skill-root", skill_root, cwd=skill_root)

    assert result.returncode != 0
    assert "Runtime Python interpreter mismatch" in result.stderr
    assert f"expected_identity={runtime_python}" in result.stderr
    assert f"actual_identity={sys.executable}" in result.stderr


def test_runtime_smoke_rejects_repo_development_venv_when_runtime_venv_expected(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _create_runtime_venv(skill_root)
    repo_dev_python = REPO_ROOT / ".venv" / "bin" / "python"
    assert repo_dev_python.exists()

    result = _run_smoke(repo_dev_python, smoke_path, "--skill-root", skill_root, cwd=skill_root)

    assert result.returncode != 0
    assert "Runtime Python interpreter mismatch" in result.stderr
    assert f"expected_identity={runtime_python}" in result.stderr
    assert f"actual_identity={repo_dev_python}" in result.stderr


def test_runtime_smoke_rejects_host_python_even_when_runtime_venv_symlinks_to_same_binary(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _create_runtime_venv(skill_root)
    assert os.path.realpath(runtime_python) == os.path.realpath(sys.executable)

    result = _run_smoke(sys.executable, smoke_path, "--skill-root", skill_root, cwd=skill_root)

    assert result.returncode != 0
    assert "Runtime Python interpreter mismatch" in result.stderr
    assert f"expected_identity={runtime_python}" in result.stderr
    assert f"actual_identity={sys.executable}" in result.stderr


def test_runtime_smoke_accepts_only_explicit_runtime_venv_python_after_trap_preflight_exists(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    trap_root = tmp_path / "trap-ambient"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _create_runtime_venv(skill_root)
    trap_python = _create_runtime_venv(trap_root)

    trap_result = _run_smoke(trap_python, smoke_path, "--skill-root", skill_root, cwd=skill_root)
    runtime_result = _run_smoke(runtime_python, smoke_path, "--skill-root", skill_root, cwd=skill_root)

    assert trap_result.returncode != 0
    assert "Runtime Python interpreter mismatch" in trap_result.stderr
    assert runtime_result.returncode == 0, runtime_result.stderr
    assert "runtime smoke ok:" in runtime_result.stdout
    assert "yaml" in runtime_result.stdout
    assert "config" in runtime_result.stdout
    assert "utils_json" in runtime_result.stdout
    assert "runtime_launch_guard" in runtime_result.stdout
    assert os.path.realpath(runtime_python) in runtime_result.stdout


def test_trap_mode_preflight_does_not_leave_runtime_smoke_bound_to_trap_venv(tmp_path):
    marker_file = tmp_path / "trap-venv-marker.txt"
    preflight_fixture = tmp_path / "preflight-fixture"
    _copy_minimal_preflight_fixture(preflight_fixture)
    env = os.environ.copy()
    env["PREFLIGHT_TRAP_VENV_MARKER_FILE"] = str(marker_file)

    preflight_result = subprocess.run(
        ["bash", "preflight.sh", "--trap-mode", "--report-all"],
        cwd=str(preflight_fixture),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert preflight_result.returncode == 0, preflight_result.stdout + preflight_result.stderr
    trap_venv = Path(marker_file.read_text(encoding="utf-8").strip())
    assert trap_venv
    assert not trap_venv.exists()

    skill_root = tmp_path / "runtime-skill"
    _copy_minimal_skill_root(skill_root)
    runtime_python = _create_runtime_venv(skill_root)
    runtime_result = _run_runtime_wrapper(skill_root)

    assert runtime_result.returncode == 0, runtime_result.stderr
    assert f"expected_identity={runtime_python}" not in runtime_result.stderr
    assert str(skill_root / ".venv") in runtime_result.stdout
    assert str(trap_venv) not in runtime_result.stdout
    assert str(trap_venv) not in runtime_result.stderr
    assert "runtime smoke ok:" in runtime_result.stdout


def test_runtime_smoke_does_not_use_trap_venv():
    runtime_smoke_source = RUNTIME_SMOKE.read_text(encoding="utf-8")
    runtime_wrapper_source = RUNTIME_PYTHON_WRAPPER.read_text(encoding="utf-8")
    runtime_sources = runtime_smoke_source + "\n" + runtime_wrapper_source

    for marker in TRAP_ENV_MARKERS:
        assert marker not in runtime_sources
