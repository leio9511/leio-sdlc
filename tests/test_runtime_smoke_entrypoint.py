import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
RUNTIME_SMOKE = SCRIPTS_DIR / "runtime_smoke.py"
SMOKE_POLICY = "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation."


def _copy_minimal_skill_root(target_root):
    scripts_dir = target_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for name in ("runtime_smoke.py", "runtime_launch_guard.py", "config.py", "utils_json.py"):
        shutil.copy2(SCRIPTS_DIR / name, scripts_dir / name)
    return scripts_dir / "runtime_smoke.py"


def _make_runtime_python(skill_root):
    runtime_python = skill_root / ".venv" / "bin" / "python"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.symlink_to(sys.executable)
    return runtime_python


def _run_smoke(python, smoke_path, *args, cwd=None):
    return subprocess.run(
        [str(python), str(smoke_path), *map(str, args)],
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _snapshot(root):
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".venv" in relative.parts:
            continue
        entries.append((str(relative), "dir" if path.is_dir() else "file"))
    return entries


def test_runtime_smoke_requires_expected_runtime_venv_interpreter(tmp_path):
    skill_root = tmp_path / "fake-skill-root"
    smoke_path = _copy_minimal_skill_root(skill_root)

    result = _run_smoke(sys.executable, smoke_path, "--skill-root", skill_root, cwd=skill_root)

    assert result.returncode != 0
    assert "runtime smoke failed" in result.stderr
    assert "Runtime Python interpreter mismatch" in result.stderr
    assert "actual=" in result.stderr
    assert "expected=" in result.stderr
    assert str(skill_root / ".venv" / "bin" / "python") in result.stderr


def test_runtime_smoke_accepts_explicit_runtime_venv_python_and_imports_key_dependencies(tmp_path):
    skill_root = tmp_path / "runtime-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _make_runtime_python(skill_root)

    result = _run_smoke(
        runtime_python,
        smoke_path,
        "--skill-root",
        skill_root,
        "--expected-runtime-python",
        runtime_python,
        cwd=skill_root,
    )

    assert result.returncode == 0, result.stderr
    assert "runtime smoke ok:" in result.stdout
    assert "yaml" in result.stdout
    assert "config" in result.stdout
    assert "utils_json" in result.stdout
    assert "runtime_launch_guard" in result.stdout
    assert os.path.realpath(runtime_python) in result.stdout
    assert f"skill_root={os.path.realpath(skill_root)}" in result.stdout
    assert "startup_path=" in result.stdout


def test_runtime_smoke_is_side_effect_free(tmp_path):
    skill_root = tmp_path / "isolated-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _make_runtime_python(skill_root)
    before = _snapshot(skill_root)

    result = _run_smoke(
        runtime_python,
        smoke_path,
        "--skill-root",
        skill_root,
        "--expected-runtime-python",
        runtime_python,
        cwd=skill_root,
    )

    assert result.returncode == 0, result.stderr
    assert _snapshot(skill_root) == before
    forbidden = (".sdlc_runs", "jobs", "state", "auditor_debug", "__pycache__")
    for name in forbidden:
        assert not any(path.name == name for path in skill_root.rglob("*")), name


def test_runtime_smoke_help_documents_official_no_side_effect_policy():
    result = subprocess.run(
        [sys.executable, str(RUNTIME_SMOKE), "--help"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert SMOKE_POLICY in result.stdout
    assert "full auditor/orchestrator/long-running business execution as default smoke" in result.stdout


def test_runtime_smoke_startup_path_initialization_does_not_launch_orchestrator(tmp_path):
    skill_root = tmp_path / "startup-skill"
    smoke_path = _copy_minimal_skill_root(skill_root)
    runtime_python = _make_runtime_python(skill_root)

    result = _run_smoke(
        runtime_python,
        smoke_path,
        "--skill-root",
        skill_root,
        "--expected-runtime-python",
        runtime_python,
        cwd=skill_root,
    )

    assert result.returncode == 0, result.stderr
    assert "startup_path=" in result.stdout
    assert "runtime smoke ok:" in result.stdout
    assert not (skill_root / ".sdlc_runs").exists()
    assert not (skill_root / ".coder_session").exists()
    assert not (skill_root / "orchestrator.log").exists()
