from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_MANIFEST = REPO_ROOT / "ignore_tests.json"
SOURCE_PREFLIGHT = REPO_ROOT / "preflight.sh"
TARGETED_PYTEST_IGNORES = {
    "tests/test_orchestrator_session_strategy.py",
    "tests/test_planner_envelope_forward_compatibility.py",
}


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        _make_executable(path)


def _create_fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fixture_repo"
    repo.mkdir(parents=True)

    preflight_path = repo / "preflight.sh"
    preflight_path.write_text(SOURCE_PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    _make_executable(preflight_path)

    _write(
        repo / "ignore_tests.json",
        '{\n  "bash": [],\n  "pytest": ["tests/test_ignored_pytest.py"]\n}\n',
    )

    _write(
        repo / "tests" / "test_template_compliance.py",
        "def test_template_compliance_placeholder():\n"
        "    assert True\n",
    )

    _write(
        repo / "tests" / "test_ignored_pytest.py",
        "from pathlib import Path\n\n"
        "def test_ignored_pytest():\n"
        "    Path('order.log').write_text('ignored-ran\\n', encoding='utf-8')\n"
        "    assert False, 'ignored test was executed'\n",
    )

    _write(
        repo / "tests" / "test_allowed_pytest.py",
        "from pathlib import Path\n\n"
        "def test_allowed_pytest():\n"
        "    path = Path('order.log')\n"
        "    existing = path.read_text(encoding='utf-8') if path.exists() else ''\n"
        "    path.write_text(existing + 'allowed-ran\\n', encoding='utf-8')\n"
        "    assert True\n",
    )

    return repo


def _run_preflight(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SDLC_TEST_MODE"] = "true"
    return subprocess.run(
        ["bash", "preflight.sh", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_targeted_portability_pytests_are_not_quarantined():
    manifest = json.loads(IGNORE_MANIFEST.read_text(encoding="utf-8"))

    assert isinstance(manifest, dict)
    assert set(manifest) == {"bash", "pytest"}
    assert isinstance(manifest["bash"], list)
    assert isinstance(manifest["pytest"], list)
    assert all(isinstance(item, str) for item in manifest["bash"])
    assert all(isinstance(item, str) for item in manifest["pytest"])
    assert TARGETED_PYTEST_IGNORES.isdisjoint(manifest["pytest"])


def test_preflight_source_of_truth_still_consumes_repo_ignore_manifest(tmp_path: Path):
    preflight_script = SOURCE_PREFLIGHT.read_text(encoding="utf-8")
    assert 'IGNORE_MANIFEST="$PROJECT_DIR/ignore_tests.json"' in preflight_script
    assert 'PYTEST_IGNORE_ARGS+=("--ignore=$ignored_path")' in preflight_script

    repo = _create_fixture_repo(tmp_path)
    result = _run_preflight(repo)
    order_log = (repo / "order.log").read_text(encoding="utf-8")

    assert result.returncode == 0
    assert "debt-quarantine green" in result.stdout
    assert "ignored test was executed" not in result.stdout
    assert order_log == "allowed-ran\n"
