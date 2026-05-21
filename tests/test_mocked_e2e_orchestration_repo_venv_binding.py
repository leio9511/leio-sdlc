from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGETED_ORCHESTRATION_HARNESSES = {
    "scripts/e2e/mocked/e2e_test_1092_dual_yellow_path.sh",
    "scripts/e2e/mocked/e2e_test_job_queue_engine.sh",
    "scripts/e2e/mocked/e2e_test_orchestrator_fsm.sh",
    "scripts/e2e/mocked/e2e_test_uat_orchestrator.sh",
}
REMAINING_MOCKED_E2E_TRAP_ENTRIES: set[str] = set()
AMBIENT_CONTRACT_CALL = re.compile(
    r"(^|[;&|()[:space:]])(?:python|python3|pytest)(?:[[:space:]]|$)".replace(
        "[:space:]", "\\s"
    ),
    re.MULTILINE,
)


def _read_target(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_orchestration_mocked_e2e_targets_do_not_use_ambient_python_for_contract_critical_calls():
    offenders: dict[str, list[str]] = {}

    for relative_path in sorted(TARGETED_ORCHESTRATION_HARNESSES):
        matches = [
            line.strip()
            for line in _read_target(relative_path).splitlines()
            if AMBIENT_CONTRACT_CALL.search(line)
        ]
        if matches:
            offenders[relative_path] = matches

    assert offenders == {}


def test_orchestration_mocked_e2e_targets_reference_dev_python_or_sandbox_binding():
    missing_binding = [
        relative_path
        for relative_path in sorted(TARGETED_ORCHESTRATION_HARNESSES)
        if "dev_python.sh" not in _read_target(relative_path)
    ]

    assert missing_binding == []


def test_orchestration_mocked_e2e_targets_removed_from_trap_manifest_only():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest["bash"])

    assert bash_entries.isdisjoint(TARGETED_ORCHESTRATION_HARNESSES)
    assert REMAINING_MOCKED_E2E_TRAP_ENTRIES.issubset(bash_entries)
    assert manifest["pytest"] == []


def test_orchestration_mocked_e2e_targets_pass_under_clean_trap_venv_path(tmp_path: Path):
    trap_venv = tmp_path / "clean_trap_venv"
    subprocess.run(
        [str(REPO_ROOT / "scripts/dev_python.sh"), "-m", "venv", str(trap_venv)],
        cwd=REPO_ROOT,
        check=True,
    )
    trap_path = str(trap_venv / "bin")
    env = os.environ.copy()
    env["PATH"] = f"{trap_path}{os.pathsep}{env['PATH']}"
    env["SDLC_TEST_MODE"] = "true"

    for relative_path in sorted(TARGETED_ORCHESTRATION_HARNESSES):
        result = subprocess.run(
            ["bash", relative_path],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert result.returncode == 0, (
            f"{relative_path} failed under clean trap venv PATH\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
