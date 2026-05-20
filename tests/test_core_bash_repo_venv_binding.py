from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_BASH_TARGETS = (
    "scripts/test_cwd_guardrail.sh",
    "scripts/test_escalation_clean.sh",
    "scripts/test_missing_channel.sh",
    "scripts/test_missing_force_replan.sh",
    "scripts/test_orchestrator_logs.sh",
    "scripts/test_orchestrator_session_strategy.sh",
    "scripts/test_polyrepo_context.sh",
    "scripts/test_pr_003.sh",
)

AMBIENT_INVOCATION_RE = re.compile(
    r"(^|[;&|(){}[:space:]])(?P<cmd>python3|python|pytest)(?=\s|$)"
)
ALLOWED_AMBIENT_SNIPPETS = (
    # scripts/dev_python.sh owns repo-venv creation; these target scripts must call that wrapper.
    "scripts/dev_python.sh",
)


def _strip_single_quoted_heredocs(text: str) -> str:
    """Remove literal heredoc bodies so embedded mock Python source is not treated as shell."""
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


def test_core_bash_targets_do_not_use_ambient_python_for_contract_critical_calls():
    offenders: list[str] = []
    for rel_path in CORE_BASH_TARGETS:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        shell_text = _strip_single_quoted_heredocs(text)
        for lineno, line in enumerate(shell_text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if any(snippet in line for snippet in ALLOWED_AMBIENT_SNIPPETS):
                continue
            if AMBIENT_INVOCATION_RE.search(line):
                offenders.append(f"{rel_path}:{lineno}: {line}")

    assert not offenders, "Ambient Python/pytest invocations found:\n" + "\n".join(offenders)


def test_core_bash_targets_reference_dev_python_wrapper():
    missing = [
        rel_path
        for rel_path in CORE_BASH_TARGETS
        if "scripts/dev_python.sh" not in (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    ]

    assert not missing, "Targets missing explicit repo-local dev_python wrapper: " + ", ".join(missing)


def test_core_bash_targets_removed_from_trap_manifest():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_ignored = set(manifest.get("bash", []))
    still_ignored = sorted(set(CORE_BASH_TARGETS) & bash_ignored)

    assert not still_ignored, "Core bash targets still ignored: " + ", ".join(still_ignored)


def test_core_bash_targets_pass_with_clean_trap_ambient_python(tmp_path: Path):
    trap_venv = tmp_path / "trap_venv"
    subprocess.run([sys.executable, "-m", "venv", str(trap_venv)], check=True)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(trap_venv)
    env["SDLC_TEST_MODE"] = "true"

    failures: list[str] = []
    for rel_path in CORE_BASH_TARGETS:
        result = subprocess.run(
            ["bash", rel_path],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if result.returncode != 0:
            failures.append(
                f"{rel_path} exited {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    assert not failures, "\n\n".join(failures)
