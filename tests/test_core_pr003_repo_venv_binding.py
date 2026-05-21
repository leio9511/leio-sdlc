from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PR003_BASH_TARGET = REPO_ROOT / "scripts" / "test_pr_003.sh"
PR003_MANIFEST_ENTRY = "scripts/test_pr_003.sh"
CORE_BASH_MANIFEST_ENTRIES = {
    "scripts/test_cwd_guardrail.sh",
    "scripts/test_escalation_clean.sh",
    "scripts/test_missing_channel.sh",
    "scripts/test_missing_force_replan.sh",
    "scripts/test_orchestrator_logs.sh",
    "scripts/test_orchestrator_session_strategy.sh",
    "scripts/test_polyrepo_context.sh",
    "scripts/test_pr_003.sh",
}
AMBIENT_PYTHON_RE = re.compile(
    r"(^|[;&|(){}]|\s)(?P<cmd>python3\s+-m\s+pytest|python\s+-m\s+pytest|python3|python|pytest)(?=\s|$)"
)
ALLOWED_BOOTSTRAP_SNIPPETS = (
    # The repo-local wrapper owns explicit .venv bootstrap semantics. This
    # test verifies the PR-003 bash target calls through that wrapper instead
    # of resolving contract-critical checks from ambient PATH.
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


def _pr003_shell_lines() -> list[tuple[int, str]]:
    text = _strip_single_quoted_heredocs(PR003_BASH_TARGET.read_text(encoding="utf-8"))
    return [
        (line_number, line)
        for line_number, line in enumerate(text.splitlines(), start=1)
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_pr003_bash_target_does_not_use_ambient_python_for_contract_critical_calls():
    offenders: list[str] = []

    for line_number, line in _pr003_shell_lines():
        if any(snippet in line for snippet in ALLOWED_BOOTSTRAP_SNIPPETS):
            continue
        if AMBIENT_PYTHON_RE.search(line):
            offenders.append(f"{PR003_MANIFEST_ENTRY}:{line_number}: {line}")

    assert not offenders, "Ambient Python/pytest invocations found:\n" + "\n".join(offenders)


def test_pr003_bash_target_references_dev_python_wrapper():
    text = PR003_BASH_TARGET.read_text(encoding="utf-8")

    assert "scripts/dev_python.sh" in text
    assert "${PROJECT_ROOT}/scripts/doctor.py" in text
    assert "${PROJECT_ROOT}/scripts/orchestrator.py" in text
    assert '"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/doctor.py"' in text
    assert '"$DEV_PYTHON" "${PROJECT_ROOT}/scripts/orchestrator.py"' in text


def test_pr003_target_removed_from_trap_manifest():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest.get("bash", []))

    assert PR003_MANIFEST_ENTRY not in bash_entries
    assert CORE_BASH_MANIFEST_ENTRIES.isdisjoint(bash_entries)
    assert set(manifest) <= {"bash", "pytest"}


def test_pr003_bash_target_passes_with_clean_trap_venv_path(tmp_path: Path):
    trap_venv = tmp_path / "clean-ambient-trap-venv"
    venv.EnvBuilder(with_pip=False).create(trap_venv)
    trap_bin = trap_venv / "bin"

    env = os.environ.copy()
    env["PATH"] = f"{trap_bin}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(trap_venv)
    env["SDLC_TEST_MODE"] = "true"

    result = subprocess.run(
        ["bash", PR003_MANIFEST_ENTRY],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
