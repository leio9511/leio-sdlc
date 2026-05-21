from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARDRAIL_MOCKED_E2E_TARGETS = [
    Path("scripts/e2e/mocked/e2e_test_forensic_quarantine.sh"),
    Path("scripts/e2e/mocked/e2e_test_git_boundary.sh"),
    Path("scripts/e2e/mocked/e2e_test_hierarchical_resilience.sh"),
    Path("scripts/e2e/mocked/e2e_test_ignition_guardrail.sh"),
]
REMAINING_MOCKED_E2E_TRAP_ENTRIES: set[str] = set()


def _script_text(path: Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _contract_lines(path: Path) -> list[str]:
    lines = []
    for line in _script_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("cat ") or stripped.startswith("echo "):
            continue
        if "python" in stripped or "pytest" in stripped:
            lines.append(stripped)
    return lines


def test_guardrail_mocked_e2e_targets_do_not_use_ambient_python_for_contract_critical_calls():
    ambient_pattern = re.compile(
        r"(^|[;&|()`$\s])(?:SDLC_TEST_MODE=true\s+)?(?:python3?|pytest)(?:\s|$)"
    )

    offenders: dict[str, list[str]] = {}
    for target in GUARDRAIL_MOCKED_E2E_TARGETS:
        for line in _contract_lines(target):
            if target.name == "e2e_test_hierarchical_resilience.sh" and "python3 -m venv" in line:
                # Bootstrap allowance: deploy fixture provisions a runtime venv and then
                # runs its own runtime_python.sh contract, not project test logic.
                continue
            if ambient_pattern.search(line):
                offenders.setdefault(str(target), []).append(line)

    assert offenders == {}


def test_guardrail_mocked_e2e_targets_reference_dev_python_or_sandbox_binding():
    missing = [
        str(target)
        for target in GUARDRAIL_MOCKED_E2E_TARGETS
        if "dev_python.sh" not in _script_text(target)
    ]

    assert missing == []


def test_guardrail_mocked_e2e_targets_removed_from_trap_manifest_only():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest["bash"])
    repaired_entries = {str(target) for target in GUARDRAIL_MOCKED_E2E_TARGETS}

    assert repaired_entries.isdisjoint(bash_entries)
    assert bash_entries == REMAINING_MOCKED_E2E_TRAP_ENTRIES
    assert manifest["pytest"] == []


def test_guardrail_mocked_e2e_targets_pass_with_clean_trap_venv_path_prefix(tmp_path: Path):
    trap_venv = tmp_path / "clean_trap_venv"
    subprocess.run(["python3", "-m", "venv", str(trap_venv)], check=True)
    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["SDLC_TEST_MODE"] = "true"

    for target in GUARDRAIL_MOCKED_E2E_TARGETS:
        result = subprocess.run(
            ["bash", str(target)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, (
            f"{target} failed under clean trap venv PATH prefix\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
