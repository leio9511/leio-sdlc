from __future__ import annotations

import json
import re
import subprocess
import venv
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_BASH_SCRIPTS = (
    REPO_ROOT / "scripts" / "test_escalation_clean.sh",
    REPO_ROOT / "scripts" / "test_orchestrator_logs.sh",
    REPO_ROOT / "scripts" / "test_orchestrator_session_strategy.sh",
)
TARGET_MANIFEST_ENTRIES = tuple(
    str(path.relative_to(REPO_ROOT)) for path in TARGET_BASH_SCRIPTS
)
CONTRACT_CRITICAL_AMBIENT_PATTERNS = (
    re.compile(r"(?<![\w./-])python3(?:\s|$)"),
    re.compile(r"(?<![\w./-])python(?:\s|$)"),
    re.compile(r"(?<![\w./-])python3\s+-m\s+pytest(?:\s|$)"),
    re.compile(r"(?<![\w./-])python\s+-m\s+pytest(?:\s|$)"),
    re.compile(r"(?<![\w./-])pytest(?:\s|$)"),
)


def _script_text(path: Path) -> str:
    assert path.is_file(), f"Missing expected orchestrator bash target: {path}"
    return path.read_text(encoding="utf-8")


def _meaningful_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_orchestrator_bash_targets_do_not_use_ambient_python_for_contract_critical_calls():
    offenders: list[str] = []

    for path in TARGET_BASH_SCRIPTS:
        for line_number, line in enumerate(_meaningful_lines(_script_text(path)), start=1):
            for pattern in CONTRACT_CRITICAL_AMBIENT_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line}")

    assert not offenders, "Contract-critical Python calls must not use ambient Python:\n" + "\n".join(offenders)


def test_orchestrator_bash_targets_reference_dev_python_wrapper():
    for path in TARGET_BASH_SCRIPTS:
        text = _script_text(path)
        assert "scripts/dev_python.sh" in text, f"{path.relative_to(REPO_ROOT)} must use repo-local dev_python wrapper"


def test_orchestrator_bash_targets_removed_from_trap_manifest():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))
    bash_entries = set(manifest.get("bash", []))

    for entry in TARGET_MANIFEST_ENTRIES:
        assert entry not in bash_entries


def test_orchestrator_bash_targets_pass_with_clean_trap_venv_path(tmp_path: Path):
    trap_venv = tmp_path / "ambient-trap-venv"
    venv.EnvBuilder(with_pip=False).create(trap_venv)
    trap_bin = trap_venv / "bin"

    for path in TARGET_BASH_SCRIPTS:
        result = subprocess.run(
            ["bash", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ,
                "PATH": f"{trap_bin}{subprocess.os.pathsep}{subprocess.os.environ['PATH']}",
                "SDLC_TEST_MODE": "true",
            },
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, (
            f"{path.relative_to(REPO_ROOT)} failed under clean trap venv PATH\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
