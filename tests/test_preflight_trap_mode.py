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
            "python3 -c 'import yaml'\n",
            executable=True,
        )

    return repo


def _run_preflight(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
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
