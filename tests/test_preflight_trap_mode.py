from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PREFLIGHT = REPO_ROOT / "preflight.sh"
TRAP_BANNER = (
    "TRAP REMEDIATION PENDING\n"
    "This preflight run is green only under the temporary existing ignore-manifest "
    "rollout for trap-mode failures.\n"
    "Remaining trap failures must be burned down to zero before this issue is complete."
)
TRAP_CLEAN_BANNER = (
    "TRAP MODE CLEAN\n"
    "Trap-mode preflight passed with no remaining trap remediation entries."
)
REPAIRED_ORCHESTRATOR_BASH_TARGETS = {
    "scripts/test_escalation_clean.sh",
    "scripts/test_orchestrator_logs.sh",
    "scripts/test_orchestrator_session_strategy.sh",
}
REMAINING_TRAP_BASH_TARGETS = [
    "scripts/test_pr_003.sh",
    "scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh",
    "scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh",
    "scripts/e2e/mocked/e2e_test_forensic_quarantine.sh",
    "scripts/e2e/mocked/e2e_test_git_boundary.sh",
    "scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh",
    "scripts/e2e/mocked/e2e_test_ignition_guardrail.sh",
    "scripts/e2e/mocked/e2e_test_job_queue_engine.sh",
    "scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh",
    "scripts/e2e/mocked/e2e_test_preflight_guardrails.sh",
    "scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh",
    "scripts/e2e/mocked/e2e_test_uat_orchestrator.sh",
]


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        _make_executable(path)


def _create_fixture_repo(
    tmp_path: Path,
    *,
    bash_manifest: list[str] | None = None,
    include_hostile_bash: bool = True,
    hostile_command: str = "python3 -c 'import yaml'",
) -> Path:
    repo = tmp_path / "fixture_repo"
    repo.mkdir(parents=True)

    preflight_path = repo / "preflight.sh"
    preflight_path.write_text(SOURCE_PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    _make_executable(preflight_path)

    manifest = {"bash": bash_manifest or [], "pytest": []}
    _write(repo / "ignore_tests.json", json.dumps(manifest, indent=2) + "\n")

    _write(
        repo / "scripts" / "dev_python.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {sys.executable} \"$@\"\n",
        executable=True,
    )

    _write(
        repo / "TEMPLATES" / "placeholder.md.template",
        "---\n"
        "status: pending\n"
        "---\n",
    )

    _write(
        repo / "scripts" / "structured_state_parser.py",
        "from pathlib import Path\n\n"
        "VALID_STATES = {'pending', 'in_progress', 'completed'}\n\n"
        "def get_status(path):\n"
        "    text = Path(path).read_text(encoding='utf-8')\n"
        "    for line in text.splitlines():\n"
        "        if line.startswith('status:'):\n"
        "            return line.split(':', 1)[1].strip()\n"
        "    return None\n",
    )

    _write(
        repo / "tests" / "test_template_compliance.py",
        (REPO_ROOT / "tests" / "test_template_compliance.py").read_text(encoding="utf-8"),
    )
    _write(
        repo / "tests" / "test_allowed.py",
        "def test_allowed_placeholder():\n"
        "    assert True\n",
    )

    if include_hostile_bash:
        _write(
            repo / "scripts" / "test_ambient_yaml.sh",
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"{hostile_command}\n",
            executable=True,
        )

    return repo


def _run_preflight(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    run_env["SDLC_TEST_MODE"] = "true"
    if env:
        run_env.update(env)
    return subprocess.run(
        ["bash", "preflight.sh", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=run_env,
        timeout=timeout,
        check=False,
    )


def test_trap_mode_cli_flag_is_accepted_and_unknown_flags_still_fail(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, include_hostile_bash=False)

    accepted = _run_preflight(repo, "--trap-mode", "--report-all")
    rejected = _run_preflight(repo, "--trap-mode", "--definitely-unknown")

    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert rejected.returncode != 0
    assert "Unknown argument: --definitely-unknown" in rejected.stdout


def test_trap_mode_uses_clean_ambient_python_without_project_dependencies(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path)

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode != 0
    assert "Bash Test: scripts/test_ambient_yaml.sh" in result.stdout
    assert "No module named yaml" in result.stdout or "No module named 'yaml'" in result.stdout


def test_trap_mode_masks_host_pytest_with_hostile_trap_pytest(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, hostile_command="pytest --version")
    host_bin = tmp_path / "host_bin"
    host_bin.mkdir()
    _write(
        host_bin / "pytest",
        "#!/usr/bin/env bash\n"
        "echo HOST PYTEST SHOULD NOT RUN\n"
        "exit 0\n",
        executable=True,
    )

    result = _run_preflight(
        repo,
        "--trap-mode",
        "--report-all",
        env={"PATH": f"{host_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode != 0
    assert "Bash Test: scripts/test_ambient_yaml.sh" in result.stdout
    assert "HOST PYTEST SHOULD NOT RUN" not in result.stdout


def test_trap_mode_prints_clean_banner_when_manifest_empty(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, include_hostile_bash=False)

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode == 0, result.stdout + result.stderr
    assert TRAP_CLEAN_BANNER in result.stdout
    assert TRAP_BANNER not in result.stdout


def test_trap_mode_does_not_modify_repo_venv_and_cleans_temp_venv(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, bash_manifest=["scripts/test_ambient_yaml.sh"])
    repo_venv = repo / ".venv"
    repo_venv.mkdir()
    sentinel = repo_venv / "sentinel.txt"
    sentinel.write_text("keep me\n", encoding="utf-8")
    marker_file = tmp_path / "trap_venv_path.txt"

    result = _run_preflight(
        repo,
        "--trap-mode",
        "--report-all",
        env={"PREFLIGHT_TRAP_VENV_MARKER_FILE": str(marker_file)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep me\n"
    trap_venv_path = Path(marker_file.read_text(encoding="utf-8").strip())
    assert trap_venv_path != repo_venv
    assert not trap_venv_path.exists()


def test_trap_quarantine_banner_is_printed_for_non_empty_manifest(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, bash_manifest=["scripts/test_ambient_yaml.sh"])

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode == 0, result.stdout + result.stderr
    assert TRAP_BANNER in result.stdout
    assert "debt-quarantine green" not in result.stdout


def test_slice_trap_preflight_stays_green_with_repaired_orchestrator_targets_removed(tmp_path: Path):
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest["bash"])

    assert REPAIRED_ORCHESTRATOR_BASH_TARGETS.isdisjoint(bash_entries)

    repo = _create_fixture_repo(
        tmp_path,
        bash_manifest=REMAINING_TRAP_BASH_TARGETS,
        include_hostile_bash=False,
    )
    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode == 0, result.stdout + result.stderr
    assert TRAP_BANNER in result.stdout
    assert "✅" in result.stdout
    assert "TRAP MODE CLEAN" not in result.stdout
    assert f"{len(REMAINING_TRAP_BASH_TARGETS)} bash target(s)" not in result.stdout
    assert "debt-quarantine green" not in result.stdout
    assert "scripts/test_escalation_clean.sh" not in result.stdout
    assert "scripts/test_orchestrator_logs.sh" not in result.stdout
    assert "scripts/test_orchestrator_session_strategy.sh" not in result.stdout


def test_slice_normal_preflight_stays_green_with_remaining_trap_debt_only(tmp_path: Path):
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest["bash"])

    assert REPAIRED_ORCHESTRATOR_BASH_TARGETS.isdisjoint(bash_entries)
    assert set(REMAINING_TRAP_BASH_TARGETS).issubset(bash_entries)
    assert len(manifest["bash"]) == 12

    repo = _create_fixture_repo(
        tmp_path,
        bash_manifest=REMAINING_TRAP_BASH_TARGETS,
        include_hostile_bash=False,
    )
    result = _run_preflight(repo, "--report-all")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "debt-quarantine green" in result.stdout
    assert f"{len(REMAINING_TRAP_BASH_TARGETS)} bash target(s)" in result.stdout
    assert TRAP_BANNER not in result.stdout
