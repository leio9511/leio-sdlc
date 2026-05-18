import os
import subprocess
import sys
import venv
from pathlib import Path

from scripts.runtime_launch_guard import (
    RUNTIME_EXECUTION_CONTEXT_DESCRIPTION,
    RuntimeInterpreterMismatch,
    resolve_expected_runtime_python,
    resolve_runtime_skill_root,
    runtime_python_for_skill_root,
    validate_runtime_interpreter,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "runtime_smoke.py"
SMOKE_POLICY = "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation."


def _canonical(path):
    return os.path.realpath(os.path.abspath(os.fspath(path)))


def _venv_python(skill_root):
    return skill_root / ".venv" / "bin" / "python"


def test_resolve_runtime_skill_root_prefers_explicit_root_then_env_then_script_path(tmp_path):
    explicit_root = tmp_path / "explicit-skill"
    env_root = tmp_path / "env-skill"
    script_root = tmp_path / "script-skill"
    script_path = script_root / "scripts" / "runtime_launch_guard.py"

    assert resolve_runtime_skill_root(
        skill_root=explicit_root,
        script_path=script_path,
        env={"LEIO_SDLC_SKILL_ROOT": str(env_root)},
    ) == _canonical(explicit_root)
    assert resolve_runtime_skill_root(
        script_path=script_path,
        env={"LEIO_SDLC_SKILL_ROOT": str(env_root)},
    ) == _canonical(env_root)
    assert resolve_runtime_skill_root(script_path=script_path, env={}) == _canonical(script_root)


def test_expected_runtime_python_defaults_to_skill_root_venv_python(tmp_path):
    skill_root = tmp_path / "skill-root"

    expected_python = resolve_expected_runtime_python(skill_root=skill_root, env={})

    assert expected_python == _canonical(skill_root / ".venv" / "bin" / "python")
    assert expected_python != _canonical(sys.executable)
    assert os.path.basename(expected_python) == "python"


def test_expected_runtime_python_can_be_overridden_for_contract_checks(tmp_path):
    skill_root = tmp_path / "skill-root"
    explicit_python = tmp_path / "explicit" / "bin" / "python"
    env_python = tmp_path / "env" / "bin" / "python"

    assert resolve_expected_runtime_python(
        skill_root=skill_root,
        expected_python=explicit_python,
        env={"LEIO_SDLC_RUNTIME_PYTHON": str(env_python)},
    ) == _canonical(explicit_python)
    assert resolve_expected_runtime_python(
        skill_root=skill_root,
        env={"LEIO_SDLC_RUNTIME_PYTHON": str(env_python)},
    ) == _canonical(env_python)
    assert runtime_python_for_skill_root(skill_root) == _canonical(skill_root / ".venv" / "bin" / "python")


def test_validate_runtime_interpreter_accepts_matching_canonical_runtime_python(tmp_path):
    skill_root = tmp_path / "skill-root"
    runtime_python = skill_root / ".venv" / "bin" / "python"
    runtime_python.parent.mkdir(parents=True)
    runtime_python.write_text("#!/bin/sh\n", encoding="utf-8")
    relative_actual_python = runtime_python.parent / ".." / "bin" / "python"

    assert validate_runtime_interpreter(
        actual_python=relative_actual_python,
        skill_root=skill_root,
        env={},
    ) == _canonical(runtime_python)


def test_validate_runtime_interpreter_fails_closed_with_actual_expected_and_context(tmp_path):
    skill_root = tmp_path / "skill-root"
    actual_python = tmp_path / "ambient" / "bin" / "python"
    expected_python = skill_root / ".venv" / "bin" / "python"

    try:
        validate_runtime_interpreter(actual_python=actual_python, skill_root=skill_root, env={})
    except RuntimeInterpreterMismatch as exc:
        diagnostic = str(exc)
    else:
        raise AssertionError("Expected runtime interpreter validation to fail closed.")

    assert "actual=" in diagnostic
    assert "expected=" in diagnostic
    assert _canonical(actual_python) in diagnostic
    assert _canonical(expected_python) in diagnostic
    assert RUNTIME_EXECUTION_CONTEXT_DESCRIPTION in diagnostic



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


def _run_smoke(python, *args, cwd=None, smoke_script=SMOKE_SCRIPT):
    return subprocess.run(
        [str(python), str(smoke_script), *map(str, args)],
        cwd=str(cwd or REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _snapshot_tree(root):
    if not root.exists():
        return {}
    snapshot = {}
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if ".venv" in relative_parts:
            continue
        relative_path = path.relative_to(root).as_posix()
        if path.is_file():
            stat = path.stat()
            snapshot[relative_path] = ("file", stat.st_size, stat.st_mtime_ns)
        elif path.is_dir():
            snapshot[relative_path] = ("dir",)
        else:
            snapshot[relative_path] = ("other",)
    return snapshot


def _copy_minimal_smoke_skill(source_root, target_root):
    scripts_dir = target_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for filename in (
        "runtime_smoke.py",
        "runtime_launch_guard.py",
        "config.py",
        "utils_json.py",
    ):
        (scripts_dir / filename).write_text(
            (source_root / "scripts" / filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _workflow_text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _ci_runtime_smoke_command():
    workflow_text = _workflow_text()
    for block in workflow_text.split("\n\n"):
        if "id: run-runtime-smoke" in block:
            return block
    raise AssertionError("Expected preflight workflow to define run-runtime-smoke step.")


def test_ci_smoke_command_matches_official_runtime_smoke_entrypoint():
    command = _ci_runtime_smoke_command()

    assert "scripts/runtime_smoke.py" in command
    assert SMOKE_SCRIPT.name in command
    assert "scripts/dev_python.sh" in command or ".venv/bin/python" in command
    assert "--expected-runtime-python" in command
    assert "ci_runtime_smoke" not in command
    assert "ci-smoke" not in command
    assert "python3 scripts/runtime_smoke.py" not in command


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
    assert f"skill_root={os.path.realpath(skill_root)}" in result.stdout
    assert f"startup_path={os.path.realpath(SMOKE_SCRIPT.parent)}" in result.stdout
    assert "yaml:" in result.stdout
    assert "config" in result.stdout
    assert "utils_json" in result.stdout
    assert "runtime_launch_guard" in result.stdout


def test_runtime_smoke_is_side_effect_free(tmp_path):
    skill_root = tmp_path / "isolated-skill-root"
    _copy_minimal_smoke_skill(REPO_ROOT, skill_root)
    runtime_python = _make_runtime_venv(skill_root)
    smoke_script = skill_root / "scripts" / "runtime_smoke.py"
    forbidden_names = {
        ".sdlc_runs",
        "job_dir",
        "STATE.md",
        "state.json",
        ".sdlc.lock",
        "spawned_agents",
        "auditor_debug",
        "__pycache__",
    }

    before_skill = _snapshot_tree(skill_root)
    before_repo_scripts = _snapshot_tree(REPO_ROOT / "scripts")
    result = _run_smoke(
        runtime_python,
        "--skill-root",
        skill_root,
        cwd=skill_root,
        smoke_script=smoke_script,
    )
    after_skill = _snapshot_tree(skill_root)
    after_repo_scripts = _snapshot_tree(REPO_ROOT / "scripts")

    assert result.returncode == 0, result.stderr
    assert f"skill_root={os.path.realpath(skill_root)}" in result.stdout
    assert f"startup_path={os.path.realpath(smoke_script.parent)}" in result.stdout
    assert after_skill == before_skill
    assert after_repo_scripts == before_repo_scripts
    assert all(name not in path.split("/") for path in after_skill for name in forbidden_names)


def test_runtime_smoke_help_documents_official_no_side_effect_policy():
    result = _run_smoke(sys.executable, "--help")

    assert result.returncode == 0
    assert "Official minimal no-side-effect leio-sdlc runtime smoke path" in result.stdout
    assert SMOKE_POLICY in result.stdout
    assert "full auditor/orchestrator/long-running business execution" in result.stdout
    assert "Run full auditor" not in result.stdout
    assert "Run orchestrator" not in result.stdout
