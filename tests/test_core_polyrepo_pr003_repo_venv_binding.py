from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


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
TARGET_BASH_TARGETS = (
    "scripts/test_polyrepo_context.sh",
    "scripts/test_pr_003.sh",
)
AMBIENT_INVOCATION_RE = re.compile(
    r"(^|[;&|(){}]|\s)(?P<cmd>python3|python|pytest)(?=\s|$)"
)
ALLOWED_AMBIENT_SNIPPETS = (
    # The target scripts may refer to the repo-local wrapper path; that wrapper
    # owns repo .venv bootstrap semantics outside this regression scope.
    "scripts/dev_python.sh",
)
PREFLIGHT_ACCEPTANCE_RECURSION_GUARD = "LEIO_FULL_PREFLIGHT_ACCEPTANCE_CHILD"
PREFLIGHT_ACCEPTANCE_OPT_IN = "LEIO_RUN_FULL_PREFLIGHT_ACCEPTANCE"
PREFLIGHT_ACCEPTANCE_COMMANDS = (
    (
        "trap-mode full preflight",
        ["bash", "preflight.sh", "--trap-mode", "--report-all"],
        (
            "TRAP REMEDIATION PENDING",
            "Remaining trap failures must be burned down to zero before this issue is complete.",
            "✅ 30 tests/test-suites passed.",
        ),
    ),
    (
        "normal full preflight",
        ["bash", "preflight.sh", "--report-all"],
        (
            "Debt quarantine ignored 11 bash target(s) and 0 pytest target(s).",
            "✅ 30 tests/test-suites passed.",
        ),
    ),
)


def _strip_single_quoted_heredocs(text: str) -> str:
    """Remove literal heredoc bodies so embedded mock source is not treated as shell."""
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


def _meaningful_shell_lines(rel_path: str) -> list[tuple[int, str]]:
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    shell_text = _strip_single_quoted_heredocs(text)
    lines: list[tuple[int, str]] = []
    for line_number, line in enumerate(shell_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append((line_number, line))
    return lines


def test_polyrepo_pr003_bash_targets_do_not_use_ambient_python_for_contract_critical_calls():
    offenders: list[str] = []

    for rel_path in TARGET_BASH_TARGETS:
        for line_number, line in _meaningful_shell_lines(rel_path):
            if any(snippet in line for snippet in ALLOWED_AMBIENT_SNIPPETS):
                continue
            if AMBIENT_INVOCATION_RE.search(line):
                offenders.append(f"{rel_path}:{line_number}: {line}")

    assert not offenders, "Ambient Python/pytest invocations found:\n" + "\n".join(offenders)


def test_polyrepo_pr003_bash_targets_reference_dev_python_wrapper():
    missing = [
        rel_path
        for rel_path in TARGET_BASH_TARGETS
        if "scripts/dev_python.sh" not in (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    ]

    assert not missing, "Targets missing explicit repo-local dev_python wrapper: " + ", ".join(missing)


def test_all_core_bash_targets_removed_from_trap_manifest():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_ignored = set(manifest.get("bash", []))
    still_ignored = sorted(set(CORE_BASH_TARGETS) & bash_ignored)

    assert not still_ignored, "Core bash targets still ignored: " + ", ".join(still_ignored)


def test_real_repository_full_preflight_acceptance_commands_pass():
    """Run the contract's real full-preflight acceptance gates without recursion.

    ``preflight.sh`` runs the full pytest suite, which includes this test. The
    guard below lets the child preflight's pytest invocation skip only this
    recursive acceptance test while still executing the repository preflight
    commands and the rest of the suite.
    """
    if os.environ.get(PREFLIGHT_ACCEPTANCE_OPT_IN) != "1":
        pytest.skip(
            f"set {PREFLIGHT_ACCEPTANCE_OPT_IN}=1 to run full real-repository preflight acceptance gates"
        )
    if os.environ.get(PREFLIGHT_ACCEPTANCE_RECURSION_GUARD) == "1":
        pytest.skip("recursive child preflight run")

    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "PATH", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "TMPDIR", "TERM"}
    }
    env[PREFLIGHT_ACCEPTANCE_RECURSION_GUARD] = "1"
    env["PYTEST_ADDOPTS"] = "--ignore=tests/test_core_polyrepo_pr003_repo_venv_binding.py"

    failures: list[str] = []
    for desc, command, expected_markers in PREFLIGHT_ACCEPTANCE_COMMANDS:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        combined_output = result.stdout + result.stderr
        if result.returncode != 0:
            failures.append(
                f"{desc} exited {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
            continue
        missing = [marker for marker in expected_markers if marker not in combined_output]
        if missing:
            failures.append(
                f"{desc} missing expected marker(s): {missing}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

    assert not failures, "\n\n".join(failures)


def test_polyrepo_pr003_bash_targets_pass_with_clean_trap_ambient_python(tmp_path: Path):
    trap_venv = tmp_path / "trap_venv"
    subprocess.run([sys.executable, "-m", "venv", str(trap_venv)], check=True)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["VIRTUAL_ENV"] = str(trap_venv)
    env["SDLC_TEST_MODE"] = "true"

    failures: list[str] = []
    for rel_path in TARGET_BASH_TARGETS:
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
