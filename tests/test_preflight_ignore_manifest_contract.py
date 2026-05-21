"""Preflight ignore-manifest contract tests.

This module is a regression guard for PR-002: it locks in the contract that
the repaired portability pytest targets are no longer quarantined by
preflight and that the checked-in ``ignore_tests.json`` remains the
source of truth consumed by ``preflight.sh``.

If either targeted test is re-added to the ignore manifest, or if the
manifest is malformed, or if preflight stops consuming the repo-root
manifest, these tests will fail.
"""

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

ALLOWED_NON_MOCKED_E2E_TRAP_ENTRY = "scripts/test_ambient_yaml.sh"
REPAIRED_TEST_MODE_LEAKAGE_TARGET = "scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh"
REPAIRED_MOCKED_E2E_ORCHESTRATION_TARGETS = {
    "scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh",
    "scripts/e2e/mocked/e2e_test_job_queue_engine.sh",
    "scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh",
    "scripts/e2e/mocked/e2e_test_uat_orchestrator.sh",
}
REPAIRED_PREFLIGHT_GUARDRAILS_TARGET = "scripts/e2e/mocked/e2e_test_preflight_guardrails.sh"
REPAIRED_GUARDRAIL_MOCKED_E2E_TARGETS = {
    "scripts/e2e/mocked/e2e_test_forensic_quarantine.sh",
    "scripts/e2e/mocked/e2e_test_git_boundary.sh",
    "scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh",
    "scripts/e2e/mocked/e2e_test_ignition_guardrail.sh",
}
PRD_TARGETED_MOCKED_E2E_TARGETS = {
    REPAIRED_TEST_MODE_LEAKAGE_TARGET,
    *REPAIRED_MOCKED_E2E_ORCHESTRATION_TARGETS,
    REPAIRED_PREFLIGHT_GUARDRAILS_TARGET,
    *REPAIRED_GUARDRAIL_MOCKED_E2E_TARGETS,
    "scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh",
}


def _assert_manifest_allows_only_non_mocked_e2e_trap_debt(manifest: dict[str, object]) -> None:
    assert isinstance(manifest, dict)
    assert set(manifest) == {"bash", "pytest"}
    assert isinstance(manifest["bash"], list)
    assert isinstance(manifest["pytest"], list)
    assert all(isinstance(item, str) for item in manifest["bash"])
    assert all(isinstance(item, str) for item in manifest["pytest"])

    quarantined_entries = set(manifest["bash"]) | set(manifest["pytest"])
    assert PRD_TARGETED_MOCKED_E2E_TARGETS.isdisjoint(quarantined_entries)


def test_mocked_e2e_manifest_burn_down_does_not_require_global_empty_manifest_yet():
    manifest = json.loads(IGNORE_MANIFEST.read_text(encoding="utf-8"))
    _assert_manifest_allows_only_non_mocked_e2e_trap_debt(manifest)

    rollout_manifest_with_non_mocked_e2e_debt = {
        "bash": [ALLOWED_NON_MOCKED_E2E_TRAP_ENTRY],
        "pytest": [],
    }
    _assert_manifest_allows_only_non_mocked_e2e_trap_debt(
        rollout_manifest_with_non_mocked_e2e_debt
    )
    # PR-003 proves mocked-E2E burn-down only.  Non-mocked-E2E trap debt may
    # still use the temporary rollout manifest and print TRAP REMEDIATION
    # PENDING; PR-004 owns final global empty-manifest enforcement.


def test_ignore_manifest_initialized_only_with_prd_trap_targets():
    manifest = json.loads(IGNORE_MANIFEST.read_text(encoding="utf-8"))

    _assert_manifest_allows_only_non_mocked_e2e_trap_debt(manifest)
    assert REPAIRED_TEST_MODE_LEAKAGE_TARGET not in manifest["bash"]
    assert REPAIRED_TEST_MODE_LEAKAGE_TARGET not in manifest["pytest"]
    assert REPAIRED_PREFLIGHT_GUARDRAILS_TARGET not in manifest["bash"]
    assert REPAIRED_GUARDRAIL_MOCKED_E2E_TARGETS.isdisjoint(manifest["bash"])
    assert REPAIRED_MOCKED_E2E_ORCHESTRATION_TARGETS.isdisjoint(manifest["bash"])


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

    _write(
        repo / "scripts" / "dev_python.sh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "exec python3 \"$@\"\n",
        executable=True,
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
    """The checked-in ignore manifest must parse cleanly and must NOT
    quarantine either of the repaired portability pytest targets.

    Validates manifest shape (must be a dict with exactly ``bash`` and
    ``pytest`` keys whose values are arrays of strings) to prevent a
    fake fix via malformed JSON, deleted keys, or non-array values.
    """
    manifest = json.loads(IGNORE_MANIFEST.read_text(encoding="utf-8"))

    assert isinstance(manifest, dict)
    assert set(manifest) == {"bash", "pytest"}
    assert isinstance(manifest["bash"], list)
    assert isinstance(manifest["pytest"], list)
    assert all(isinstance(item, str) for item in manifest["bash"])
    assert all(isinstance(item, str) for item in manifest["pytest"])
    assert TARGETED_PYTEST_IGNORES.isdisjoint(manifest["pytest"])


def test_preflight_source_of_truth_still_consumes_repo_ignore_manifest(tmp_path: Path):
    """Verify that ``preflight.sh`` reads the repo-root ``ignore_tests.json``
    and translates each ``pytest`` entry into a ``--ignore=...`` argument so
    that re-addition of the targeted paths would be a detectable regression
    rather than a silent quarantine.
    """
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

    # Verify the quarantine count matches the manifest: 1 pytest entry
    # was ignored, confirming preflight consumed it from ignore_tests.json.
    assert "1 pytest target(s)" in result.stdout
