from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_MANIFEST = REPO_ROOT / "ignore_tests.json"
SOURCE_PREFLIGHT = REPO_ROOT / "preflight.sh"
FAIL_CLOSED_STATEMENT = "If ignore_tests.json is missing or malformed, preflight must fail closed."
TRAP_PENDING_BANNER = (
    "TRAP REMEDIATION PENDING\n"
    "This preflight run is green only under the temporary existing ignore-manifest "
    "rollout for trap-mode failures.\n"
    "Remaining trap failures must be burned down to zero before this issue is complete."
)
TRAP_CLEAN_BANNER = (
    "TRAP MODE CLEAN\n"
    "Trap-mode preflight passed with no remaining trap remediation entries."
)


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        _make_executable(path)


def _create_fixture_repo(tmp_path: Path, *, manifest_content: str | None = None) -> Path:
    repo = tmp_path / "fixture_repo"
    repo.mkdir(parents=True)

    preflight_path = repo / "preflight.sh"
    preflight_path.write_text(SOURCE_PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    _make_executable(preflight_path)

    if manifest_content is not None:
        _write(repo / "ignore_tests.json", manifest_content)

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

    return repo


def _run_preflight(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    run_env["SDLC_TEST_MODE"] = "true"
    return subprocess.run(
        ["bash", "preflight.sh", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=run_env,
        timeout=300,
        check=False,
    )


AUTHORIZED_PYTEST_TRAP_ENTRIES = {
    "tests/test_080_orchestrator_dynamic_strings.py",
    "tests/test_cleanup_flag.py",
    "tests/test_commit_state.py",
    "tests/test_pr_002_orchestrator_lock.py",
    "tests/test_resume_logic_overhaul.py",
    "tests/test_resume_split.py",
    "tests/test_notification_integration.py",
    "tests/test_pr_004_rollback.py"
}

def test_checked_in_ignore_manifest_is_empty_for_final_trap_completion():
    manifest = json.loads(IGNORE_MANIFEST.read_text(encoding="utf-8"))

    assert manifest["bash"] == []
    assert set(manifest["pytest"]).issubset(AUTHORIZED_PYTEST_TRAP_ENTRIES)


def test_trap_mode_empty_manifest_prints_clean_banner_without_pending_banner(tmp_path: Path):
    repo = _create_fixture_repo(
        tmp_path,
        manifest_content=json.dumps({"bash": [], "pytest": []}, indent=2) + "\n",
    )

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode == 0, result.stdout + result.stderr
    assert TRAP_CLEAN_BANNER in result.stdout
    assert TRAP_PENDING_BANNER not in result.stdout


def test_trap_mode_still_fails_closed_for_malformed_ignore_manifest(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, manifest_content='{ "bash": [], "pytest": [ }\n')

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode != 0
    assert FAIL_CLOSED_STATEMENT in result.stdout


def test_trap_mode_still_fails_closed_when_ignore_manifest_missing(tmp_path: Path):
    repo = _create_fixture_repo(tmp_path, manifest_content=None)

    result = _run_preflight(repo, "--trap-mode", "--report-all")

    assert result.returncode != 0
    assert FAIL_CLOSED_STATEMENT in result.stdout
