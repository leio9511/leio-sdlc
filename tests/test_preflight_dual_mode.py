from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PREFLIGHT = REPO_ROOT / "preflight.sh"


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        _make_executable(path)


def _create_fixture_repo(tmp_path: Path, *, bash_scripts: list[tuple[str, str]], pytest_modules: list[tuple[str, str]] | None = None) -> Path:
    repo = tmp_path / "fixture_repo"
    repo.mkdir(parents=True)

    preflight_path = repo / "preflight.sh"
    preflight_path.write_text(SOURCE_PREFLIGHT.read_text(encoding="utf-8"), encoding="utf-8")
    _make_executable(preflight_path)

    _write(
        repo / "ignore_tests.json",
        '{\n  "bash": [],\n  "pytest": []\n}\n',
    )

    _write(
        repo / "tests" / "test_template_compliance.py",
        "from pathlib import Path\n\n"
        "def test_template_compliance_placeholder():\n"
        "    log_path = Path('order.log')\n"
        "    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else ''\n"
        "    log_path.write_text(existing + 'template\\n', encoding='utf-8')\n"
        "    assert True\n",
    )

    for relative_path, content in bash_scripts:
        _write(repo / relative_path, content, executable=True)

    for relative_path, content in pytest_modules or []:
        _write(repo / relative_path, content)

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


def test_default_preflight_command_is_fail_fast(tmp_path: Path):
    repo = _create_fixture_repo(
        tmp_path,
        bash_scripts=[
            (
                "scripts/test_010_first_failure.sh",
                "#!/bin/bash\n"
                "echo 'first-failure' >> order.log\n"
                "echo 'first bash failure'\n"
                "exit 1\n",
            ),
            (
                "scripts/test_020_late_observable.sh",
                "#!/bin/bash\n"
                "echo 'late-bash' >> order.log\n"
                "exit 0\n",
            ),
        ],
        pytest_modules=[
            (
                "tests/test_late_pytest_probe.py",
                "from pathlib import Path\n\n"
                "def test_late_pytest_probe():\n"
                "    Path('order.log').write_text(Path('order.log').read_text(encoding='utf-8') + 'late-pytest\\n', encoding='utf-8')\n"
                "    assert True\n",
            )
        ],
    )

    result = _run_preflight(repo)

    assert result.returncode != 0
    assert "❌ PREFLIGHT FAILED: Bash Test: scripts/test_010_first_failure.sh" in result.stdout
    assert "late-bash" not in (repo / "order.log").read_text(encoding="utf-8")
    assert "late-pytest" not in (repo / "order.log").read_text(encoding="utf-8")
    assert "FINAL FAILURE SUMMARY" not in result.stdout


def test_report_all_preflight_command_accumulates_multiple_failures(tmp_path: Path):
    repo = _create_fixture_repo(
        tmp_path,
        bash_scripts=[
            (
                "scripts/test_010_first_failure.sh",
                "#!/bin/bash\n"
                "echo 'first-failure' >> order.log\n"
                "echo 'first bash failure'\n"
                "exit 1\n",
            ),
            (
                "scripts/test_020_second_failure.sh",
                "#!/bin/bash\n"
                "echo 'second-failure' >> order.log\n"
                "echo 'second bash failure'\n"
                "exit 1\n",
            ),
            (
                "scripts/test_030_late_success.sh",
                "#!/bin/bash\n"
                "echo 'late-success' >> order.log\n"
                "exit 0\n",
            ),
        ],
        pytest_modules=[
            (
                "tests/test_pytest_failure_probe.py",
                "from pathlib import Path\n\n"
                "def test_pytest_failure_probe():\n"
                "    log_path = Path('order.log')\n"
                "    log_path.write_text(log_path.read_text(encoding='utf-8') + 'pytest-failure\\n', encoding='utf-8')\n"
                "    assert False, 'pytest failure probe'\n",
            )
        ],
    )

    result = _run_preflight(repo, "--report-all")
    order_log = (repo / "order.log").read_text(encoding="utf-8")

    assert result.returncode != 0
    assert "continuing due to report-all" in result.stdout
    assert "FINAL FAILURE SUMMARY (report-all)" in result.stdout
    assert "Bash Test: scripts/test_010_first_failure.sh" in result.stdout
    assert "Bash Test: scripts/test_020_second_failure.sh" in result.stdout
    assert "Pytest functional & unittest suite" in result.stdout
    assert "late-success" in order_log
    assert "pytest-failure" in order_log
    assert "template" in order_log


def test_fail_fast_and_report_all_share_the_same_gate_surface(tmp_path: Path):
    bash_scripts = [
        (
            "scripts/test_010_alpha.sh",
            "#!/bin/bash\n"
            "echo 'bash-alpha' >> order.log\n"
            "exit 0\n",
        ),
        (
            "scripts/test_020_beta.sh",
            "#!/bin/bash\n"
            "echo 'bash-beta' >> order.log\n"
            "exit 0\n",
        ),
    ]
    pytest_modules = [
        (
            "tests/test_gate_surface_probe.py",
            "from pathlib import Path\n\n"
            "def test_gate_surface_probe():\n"
            "    log_path = Path('order.log')\n"
            "    log_path.write_text(log_path.read_text(encoding='utf-8') + 'pytest-suite\\n', encoding='utf-8')\n"
            "    assert True\n",
        )
    ]

    fail_fast_repo = _create_fixture_repo(
        tmp_path / "fail_fast_case",
        bash_scripts=bash_scripts,
        pytest_modules=pytest_modules,
    )
    report_all_repo = _create_fixture_repo(
        tmp_path / "report_all_case",
        bash_scripts=bash_scripts,
        pytest_modules=pytest_modules,
    )

    fail_fast = _run_preflight(fail_fast_repo)
    report_all = _run_preflight(report_all_repo, "--report-all")

    assert fail_fast.returncode == 0
    assert report_all.returncode == 0
    expected_gate_order = "template\nbash-alpha\nbash-beta\npytest-suite\ntemplate\n"
    assert (fail_fast_repo / "order.log").read_text(encoding="utf-8") == expected_gate_order
    assert (report_all_repo / "order.log").read_text(encoding="utf-8") == expected_gate_order
    assert "Starting Smart Preflight Checks (fail-fast mode)" in fail_fast.stdout
    assert "Starting Smart Preflight Checks (report-all mode)" in report_all.stdout
    assert "FINAL FAILURE SUMMARY" not in fail_fast.stdout
    assert "FINAL FAILURE SUMMARY" not in report_all.stdout


def test_report_all_never_converts_a_failure_into_success(tmp_path: Path):
    repo = _create_fixture_repo(
        tmp_path,
        bash_scripts=[
            (
                "scripts/test_010_only_failure.sh",
                "#!/bin/bash\n"
                "echo 'only-failure' >> order.log\n"
                "exit 1\n",
            )
        ],
    )

    result = _run_preflight(repo, "--report-all")

    assert result.returncode != 0
    assert "FINAL FAILURE SUMMARY (report-all)" in result.stdout
    assert "✅" not in result.stdout
