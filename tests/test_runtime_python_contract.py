import os
import subprocess
import sys
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "runtime_smoke.py"
SMOKE_POLICY = "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation."


def _venv_python(skill_root):
    return skill_root / ".venv" / "bin" / "python"


def _make_runtime_venv(skill_root):
    venv.EnvBuilder(with_pip=True).create(skill_root / ".venv")
    python = _venv_python(skill_root)
    subprocess.run(
        [str(python), "-m", "pip", "install", "PyYAML"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return python


def _run_smoke(python, *args, cwd=None):
    return subprocess.run(
        [str(python), str(SMOKE_SCRIPT), *map(str, args)],
        cwd=str(cwd or REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _snapshot_tree(root):
    if not root.exists():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if ".venv" not in path.relative_to(root).parts
    }


def test_runtime_smoke_requires_expected_runtime_venv_interpreter(tmp_path):
    skill_root = tmp_path / "skill-root"
    expected_python = skill_root / ".venv" / "bin" / "python"
    expected_python.parent.mkdir(parents=True)
    expected_python.write_text("#!/bin/sh\n", encoding="utf-8")

    result = _run_smoke(sys.executable, "--skill-root", skill_root)

    assert result.returncode != 0
    diagnostic = result.stderr
    assert "runtime smoke failed" in diagnostic
    assert "Runtime Python interpreter mismatch" in diagnostic
    assert "actual=" in diagnostic
    assert "expected=" in diagnostic
    assert os.path.realpath(sys.executable) in diagnostic
    assert os.path.realpath(expected_python) in diagnostic


def test_runtime_smoke_accepts_explicit_runtime_venv_python_and_imports_key_dependencies(tmp_path):
    skill_root = tmp_path / "skill-root"
    runtime_python = _make_runtime_venv(skill_root)

    result = _run_smoke(runtime_python, "--expected-runtime-python", runtime_python)

    assert result.returncode == 0, result.stderr
    assert "runtime smoke ok" in result.stdout
    assert f"expected={os.path.realpath(runtime_python)}" in result.stdout
    assert "yaml:" in result.stdout
    assert "config" in result.stdout
    assert "utils_json" in result.stdout
    assert "runtime_launch_guard" in result.stdout


def test_runtime_smoke_is_side_effect_free(tmp_path):
    skill_root = tmp_path / "skill-root"
    skill_root.mkdir()
    runtime_python = _make_runtime_venv(skill_root)
    forbidden_names = {
        ".sdlc_runs",
        "job_dir",
        "STATE.md",
        "state.json",
        ".sdlc.lock",
        "spawned_agents",
        "auditor_debug",
    }

    before = _snapshot_tree(skill_root)
    result = _run_smoke(runtime_python, "--skill-root", skill_root, cwd=skill_root)
    after = _snapshot_tree(skill_root)

    assert result.returncode == 0, result.stderr
    assert after == before
    assert forbidden_names.isdisjoint(after)


def test_runtime_smoke_help_documents_official_no_side_effect_policy():
    result = _run_smoke(sys.executable, "--help")

    assert result.returncode == 0
    assert "Official minimal no-side-effect leio-sdlc runtime smoke path" in result.stdout
    assert SMOKE_POLICY in result.stdout
    assert "full auditor/orchestrator/long-running business execution" in result.stdout
    assert "Run full auditor" not in result.stdout
    assert "Run orchestrator" not in result.stdout
