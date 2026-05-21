from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
POLYREPO_BASH_TARGET = REPO_ROOT / "scripts" / "test_polyrepo_context.sh"
POLYREPO_MANIFEST_ENTRY = "scripts/test_polyrepo_context.sh"
UNRELATED_TRAP_MANIFEST_ENTRIES = {
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
}
AMBIENT_PYTHON_RE = re.compile(
    r"(^|[;&|(){}]|\s)(?P<cmd>python3\s+-m\s+pytest|python\s+-m\s+pytest|python3|python|pytest)(?=\s|$)"
)
ALLOWED_BOOTSTRAP_SNIPPETS = (
    # The repo-local wrapper owns explicit .venv bootstrap semantics; this test
    # verifies the polyrepo bash target calls through that wrapper instead of
    # resolving contract-critical checks from ambient PATH.
    "scripts/dev_python.sh",
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


def _polyrepo_shell_lines() -> list[tuple[int, str]]:
    text = _strip_single_quoted_heredocs(POLYREPO_BASH_TARGET.read_text(encoding="utf-8"))
    return [
        (line_number, line)
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_polyrepo_bash_target_does_not_use_ambient_python_for_contract_critical_calls():
    offenders: list[str] = []

    for line_number, line in _polyrepo_shell_lines():
        if any(snippet in line for snippet in ALLOWED_BOOTSTRAP_SNIPPETS):
            continue
        if AMBIENT_PYTHON_RE.search(line):
            offenders.append(f"{POLYREPO_MANIFEST_ENTRY}:{line_number}: {line}")

    assert not offenders, "Ambient Python/pytest invocations found:\n" + "\n".join(offenders)


def test_polyrepo_bash_target_references_dev_python_wrapper():
    text = POLYREPO_BASH_TARGET.read_text(encoding="utf-8")

    assert "scripts/dev_python.sh" in text
    assert "${PROJECT_ROOT}/scripts/doctor.py" in text
    assert "${PROJECT_ROOT}/scripts/orchestrator.py" in text
    assert '"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/doctor.py"' in text
    assert '"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/orchestrator.py"' in text


def test_polyrepo_target_removed_from_trap_manifest_only():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest.get("bash", []))

    assert POLYREPO_MANIFEST_ENTRY not in bash_entries
    assert UNRELATED_TRAP_MANIFEST_ENTRIES.issubset(bash_entries)
    assert set(manifest) <= {"bash", "pytest"}


def test_polyrepo_bash_target_passes_with_clean_trap_venv_path(tmp_path: Path):
    trap_venv = tmp_path / "clean-ambient-trap-venv"
    subprocess.run([sys.executable, "-m", "venv", str(trap_venv)], check=True)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(trap_venv)
    env["SDLC_TEST_MODE"] = "true"

    result = subprocess.run(
        ["bash", POLYREPO_MANIFEST_ENTRY],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
