from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE5_TIER1_RESET_HARNESS = Path("scripts/e2e/mocked/e2e_test_state5_tier1_reset.sh")
STATE5_TIER1_RESET_MANIFEST_ENTRY = str(STATE5_TIER1_RESET_HARNESS)
TEST_MODE_LEAKAGE_HARNESS = Path("scripts/e2e/mocked/e2e_test_1058_test_mode_leakage.sh")
HARNESS_MANIFEST_ENTRY = str(TEST_MODE_LEAKAGE_HARNESS)


def _harness_text(harness: Path = TEST_MODE_LEAKAGE_HARNESS) -> str:
    return (REPO_ROOT / harness).read_text(encoding="utf-8")


def _executable_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_heredoc = False
    heredoc_token = ""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if in_heredoc:
            if stripped == heredoc_token:
                in_heredoc = False
                heredoc_token = ""
            continue
        if not stripped or stripped.startswith("#"):
            continue
        heredoc_match = re.search(r"<<[-]?'?(\w+)'?", stripped)
        if heredoc_match:
            in_heredoc = True
            heredoc_token = heredoc_match.group(1)
            continue
        lines.append(stripped)

    return lines


def test_state5_tier1_reset_harness_has_no_contract_critical_ambient_python_calls():
    ambient_pattern = re.compile(r"(^|[;&|()`$\s])(?:python3?|pytest)(?:\s|$)")

    offenders = [
        line
        for line in _executable_lines(_harness_text(STATE5_TIER1_RESET_HARNESS))
        if ambient_pattern.search(line)
    ]

    assert offenders == []


def test_state5_tier1_reset_harness_references_dev_python_binding():
    text = _harness_text(STATE5_TIER1_RESET_HARNESS)

    assert 'init_hermetic_sandbox "scripts"' in text
    assert "dev_python.sh" in text

    orchestrator_invocations = [
        line
        for line in _executable_lines(text)
        if "scripts/orchestrator.py" in line and "--workdir" in line
    ]

    assert len(orchestrator_invocations) == 1
    assert all("run_sandbox_python" in line for line in orchestrator_invocations)


def test_state5_tier1_reset_removed_from_trap_manifest_only():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))

    assert STATE5_TIER1_RESET_MANIFEST_ENTRY not in manifest["bash"]
    assert STATE5_TIER1_RESET_MANIFEST_ENTRY not in manifest["pytest"]
    assert set(manifest) == {"bash", "pytest"}


def test_state5_tier1_reset_harness_passes_with_clean_trap_venv_and_hostile_pytest(tmp_path: Path):
    trap_venv = tmp_path / "clean_trap_venv"
    subprocess.run(
        [str(REPO_ROOT / "scripts/dev_python.sh"), "-m", "venv", str(trap_venv)],
        cwd=REPO_ROOT,
        check=True,
    )

    hostile_pytest = trap_venv / "bin" / "pytest"
    hostile_pytest.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'hostile ambient pytest must not be used' >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    hostile_pytest.chmod(hostile_pytest.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["SDLC_TEST_MODE"] = "true"

    result = subprocess.run(
        ["bash", str(STATE5_TIER1_RESET_HARNESS)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined_output
    assert "Tier 1 (Reset): Deleting branch and retrying." in combined_output
    assert "forensic snapshot" in combined_output
    assert "dirty_file.txt archived in snapshot" in combined_output
    assert "hostile ambient pytest must not be used" not in combined_output

def test_test_mode_leakage_harness_has_no_contract_critical_ambient_python_calls():
    ambient_pattern = re.compile(r"(^|[;&|()`$\s])(?:python3?|pytest)(?:\s|$)")

    offenders = [
        line
        for line in _executable_lines(_harness_text())
        if ambient_pattern.search(line)
    ]

    assert offenders == []


def test_test_mode_leakage_harness_references_dev_python_binding():
    text = _harness_text()

    assert "init_hermetic_sandbox \"$WORK_DIR/scripts\"" in text
    assert "dev_python.sh" in text

    orchestrator_invocations = [
        line
        for line in _executable_lines(text)
        if '"$ORCHESTRATOR"' in line and "--workdir" in line
    ]

    assert len(orchestrator_invocations) == 2
    assert all("run_sandbox_python" in line for line in orchestrator_invocations)


def test_test_mode_leakage_removed_from_trap_manifest_only():
    manifest = json.loads((REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8"))

    assert HARNESS_MANIFEST_ENTRY not in manifest["bash"]
    assert HARNESS_MANIFEST_ENTRY not in manifest["pytest"]
    assert set(manifest) == {"bash", "pytest"}


def test_test_mode_leakage_harness_passes_with_clean_trap_venv_and_hostile_pytest(tmp_path: Path):
    trap_venv = tmp_path / "clean_trap_venv"
    subprocess.run(
        [str(REPO_ROOT / "scripts/dev_python.sh"), "-m", "venv", str(trap_venv)],
        cwd=REPO_ROOT,
        check=True,
    )

    hostile_pytest = trap_venv / "bin" / "pytest"
    hostile_pytest.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'hostile ambient pytest must not be used' >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    hostile_pytest.chmod(hostile_pytest.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{trap_venv / 'bin'}{os.pathsep}{env['PATH']}"
    env["SDLC_TEST_MODE"] = "true"

    result = subprocess.run(
        ["bash", str(TEST_MODE_LEAKAGE_HARNESS)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined_output
    assert (
        "[WARNING] Running Orchestrator in TEST MODE with mocked LLMs. "
        "Production safety checks are bypassed."
    ) in combined_output
    assert "Production runtime detected but SDLC_TEST_MODE is enabled" in combined_output
    assert "hostile ambient pytest must not be used" not in combined_output
