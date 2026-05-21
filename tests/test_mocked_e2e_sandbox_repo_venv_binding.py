from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SANDBOX = REPO_ROOT / "scripts" / "e2e" / "setup_sandbox.sh"
DEV_PYTHON = REPO_ROOT / "scripts" / "dev_python.sh"
PREFLIGHT_GUARDRAILS_HARNESS = REPO_ROOT / "scripts" / "e2e" / "mocked" / "e2e_test_preflight_guardrails.sh"
PREFLIGHT_GUARDRAILS_MANIFEST_ENTRY = "scripts/e2e/mocked/e2e_test_preflight_guardrails.sh"
AMBIENT_PYTHON_RE = re.compile(
    r"(^|[;&|(){}]|\s)(?P<cmd>python3\s+-m\s+pytest|python\s+-m\s+pytest|python3|python|pytest)(?=\s|$)"
)


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


def _strip_single_quoted_heredocs(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        output.append(line)
        match = re.search(r"<<\s*'([^']+)'", line)
        if not match:
            index += 1
            continue
        delimiter = match.group(1)
        index += 1
        while index < len(lines) and lines[index] != delimiter:
            index += 1
        if index < len(lines):
            output.append(lines[index])
            index += 1
    return "\n".join(output) + "\n"


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


def test_preflight_guardrails_harness_uses_sandbox_repo_python_binding():
    text = PREFLIGHT_GUARDRAILS_HARNESS.read_text(encoding="utf-8")

    assert 'source "$PROJECT_ROOT/scripts/e2e/setup_sandbox.sh"' in text
    assert 'SANDBOX_DEV_PYTHON="scripts/dev_python.sh"' in text
    assert '"$SANDBOX_DEV_PYTHON" "$@"' in text
    assert "run_sandbox_python scripts/spawn_planner.py" in text
    assert "run_sandbox_python scripts/spawn_coder.py" in text
    assert "run_sandbox_python scripts/spawn_reviewer.py" in text
    assert "run_sandbox_python scripts/merge_code.py" in text
    assert 'exec "$PROJECT_ROOT/scripts/dev_python.sh" "\\$@"' in text


def test_preflight_guardrails_harness_has_no_contract_critical_ambient_python_calls():
    stripped = _strip_single_quoted_heredocs(
        PREFLIGHT_GUARDRAILS_HARNESS.read_text(encoding="utf-8")
    )
    offenders: list[str] = []

    for line_number, line in enumerate(stripped.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "PYTHON" in line or "run_sandbox_python" in line:
            continue
        if AMBIENT_PYTHON_RE.search(line):
            offenders.append(
                f"{PREFLIGHT_GUARDRAILS_MANIFEST_ENTRY}:{line_number}: {line}"
            )

    assert not offenders, "Ambient Python/pytest invocations found:\n" + "\n".join(offenders)


def test_preflight_guardrails_removed_from_trap_quarantine_after_binding():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))

    assert PREFLIGHT_GUARDRAILS_MANIFEST_ENTRY not in manifest["bash"]
    assert "scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh" in manifest["bash"]
    assert "scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh" in manifest["bash"]
    assert "scripts/e2e/mocked/e2e_test_uat_orchestrator.sh" not in manifest["bash"]
    assert manifest["pytest"] == []


def test_preflight_guardrails_harness_passes_with_clean_trap_venv_path(tmp_path: Path):
    trap_venv = tmp_path / "clean-ambient-trap-venv"
    subprocess.run([sys.executable, "-m", "venv", str(trap_venv)], check=True)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(trap_venv)
    env["SDLC_TEST_MODE"] = "true"

    result = subprocess.run(
        ["bash", PREFLIGHT_GUARDRAILS_MANIFEST_ENTRY],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )

    assert result.returncode == 0, result.stdout + result.stderr
