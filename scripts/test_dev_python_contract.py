import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_PYTHON = REPO_ROOT / "scripts" / "dev_python.sh"
PREFLIGHT = REPO_ROOT / "preflight.sh"
RUN_SDLC_TESTS = REPO_ROOT / "scripts" / "run_sdlc_tests.sh"
ISSUE_57_DOC = REPO_ROOT / "docs" / "Issue_57_Python_Execution_Contract.md"
PRD_ISSUE_57 = REPO_ROOT / "docs" / "PRDs" / "PRD_Issue_57_Controlled_Python_Execution_and_Runtime_Contract.md"

NONCRITICAL_PYTHON3_BUCKETS = {
    "historical docs": [REPO_ROOT / "docs" / "PRDs" / "PRD_023_Triad_Phase2.md"],
    "archived PRDs": [REPO_ROOT / "docs" / "PRs" / ".archive" / "PR_037_Micro_Slicing_Act.md"],
    "generated `.dist`": [REPO_ROOT / ".dist" / "TEMPLATES" / "organization_governance.md"],
    "templates/reference materials": [REPO_ROOT / "TEMPLATES" / "organization_governance.md"],
    "non-default mocked/e2e examples": [REPO_ROOT / "scripts" / "e2e" / "mocked" / "e2e_test_preflight_guardrails.sh"],
}
CONTRACT_CRITICAL_ACTIVE_PATHS = [
    DEV_PYTHON,
    PREFLIGHT,
    RUN_SDLC_TESTS,
    REPO_ROOT / "deploy.sh",
    REPO_ROOT / ".github" / "workflows" / "preflight.yml",
]

REQUIRED_CONTRACT_SURFACES = (
    "formal development/test entrypoints, deploy/runtime launch paths, GitHub CI default paths, "
    "and execution-contract-related smoke/tests"
)
REQUIRED_DEV_CONTEXT = "repository-root .venv"
REQUIRED_DEPENDENCY_ENTRY = (
    "requirements.txt at the repository root, currently serving runtime, development, "
    "and test dependencies together"
)
REQUIRED_CORE_GOAL = (
    "Define a controlled, repeatable Python execution contract for local development, testing, "
    "deployed skill runtime, and GitHub CI without depending on unmanaged system Python state."
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_body(text: str, name: str) -> str:
    start = text.index(f"{name}() {{")
    next_function = text.find("\n}\n\n", start)
    assert next_function != -1
    return text[start: next_function + 3]


def test_dev_python_wrapper_targets_repo_root_venv_without_activation():
    wrapper = _read(DEV_PYTHON)

    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in wrapper
    assert 'REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in wrapper
    assert 'VENV_DIR="${REPO_ROOT}/.venv"' in wrapper
    assert 'PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"' in wrapper
    assert 'REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"' in wrapper
    assert 'python3 -m venv "${VENV_DIR}"' in wrapper
    assert '"${PYTHON_BIN}" -m pip install -r "${REQUIREMENTS_FILE}"' in wrapper
    assert 'exec "${PYTHON_BIN}" "$@"' in wrapper
    assert "source .venv/bin/activate" not in wrapper

    result = subprocess.run(
        ["bash", str(DEV_PYTHON), "-c", "import sys; print(sys.executable)"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )

    executable = Path(result.stdout.strip().splitlines()[-1]).resolve()
    assert executable == (REPO_ROOT / ".venv" / "bin" / "python").resolve()


def test_preflight_routes_ignore_manifest_python_through_dev_wrapper():
    preflight = _read(PREFLIGHT)
    load_ignore_manifest = _function_body(preflight, "load_ignore_manifest")

    assert 'DEV_PYTHON="$PROJECT_DIR/scripts/dev_python.sh"' in preflight
    assert 'PYTHON_CMD=("$DEV_PYTHON")' in preflight
    assert 'if ! "${PYTHON_CMD[@]}" - "$IGNORE_MANIFEST" "$TMP_BASH_IGNORE" "$TMP_PYTEST_IGNORE"' in load_ignore_manifest
    assert 'if [[ ! -x "$DEV_PYTHON" ]]; then' in preflight
    assert 'Missing executable controlled Python wrapper' in preflight
    assert 'PYTHON_CMD=("python3")' not in preflight
    assert "python3 -" not in load_ignore_manifest
    assert "python -" not in load_ignore_manifest


def test_preflight_routes_pytest_through_dev_wrapper():
    preflight = _read(PREFLIGHT)

    assert 'run_test_argv "Template Compliance Gate" "${PYTHON_CMD[@]}" -m pytest tests/test_template_compliance.py' in preflight
    assert 'run_test_argv "Pytest functional & unittest suite" "${PYTHON_CMD[@]}" -m pytest tests/ "${PYTEST_IGNORE_ARGS[@]}"' in preflight
    assert "python3 -m pytest" not in preflight
    assert "python -m pytest" not in preflight
    commandish_preflight = preflight.replace("-m pytest", "-m_pytest")
    assert " pytest tests" not in commandish_preflight
    assert " pytest scripts" not in commandish_preflight


def test_preflight_routes_python_script_and_py_compile_checks_through_dev_wrapper():
    preflight = _read(PREFLIGHT)

    assert 'run_test_argv "Python Test: $f" "${PYTHON_CMD[@]}" "$f"' in preflight
    assert 'run_test_argv "Syntax Check: agent_driver.py" "${PYTHON_CMD[@]}" -m py_compile scripts/agent_driver.py' in preflight
    assert "python3 $f" not in preflight
    assert "python $f" not in preflight
    assert "python3 -m py_compile" not in preflight
    assert "python -m py_compile" not in preflight


def test_preflight_report_all_and_fail_fast_modes_are_preserved_under_wrapper_routing():
    preflight = _read(PREFLIGHT)

    assert 'FAIL_FAST_MODE_NAME="fail-fast"' in preflight
    assert 'REPORT_ALL_MODE_NAME="report-all"' in preflight
    assert '--report-all)' in preflight
    assert 'MODE="$REPORT_ALL_MODE_NAME"' in preflight
    assert 'if [[ "$MODE" == "$FAIL_FAST_MODE_NAME" ]]; then' in preflight
    assert 'FAILED_CHECKS+=("$desc")' in preflight
    assert 'BLOCKED_CHECKS+=("$desc :: $reason")' in preflight
    assert 'fail_ignore_manifest' in preflight
    assert 'If ignore_tests.json is missing or malformed, preflight must fail closed.' in preflight
    assert 'A non-empty ignore list may produce debt-quarantine green, which is distinct from true full green.' in preflight
    assert 'run_test_argv "Template Compliance Gate" "${PYTHON_CMD[@]}" -m pytest' in preflight
    assert 'run_test_argv "Pytest functional & unittest suite" "${PYTHON_CMD[@]}" -m pytest tests/' in preflight


def test_contract_critical_python_surfaces_are_documented_and_guarded():
    docs_and_guards = "\n".join(
        _read(path)
        for path in (ISSUE_57_DOC, PRD_ISSUE_57, Path(__file__))
        if path.exists()
    )

    assert REQUIRED_CONTRACT_SURFACES in docs_and_guards
    assert REQUIRED_DEV_CONTEXT in docs_and_guards
    assert REQUIRED_DEPENDENCY_ENTRY in docs_and_guards
    assert REQUIRED_CORE_GOAL in docs_and_guards
    assert "contract-critical surfaces" in docs_and_guards
    assert "whole-repo" in docs_and_guards
    assert "historical" in docs_and_guards


def test_noncritical_python3_scan_is_bucketed_not_global_text_purge():
    issue_doc = _read(ISSUE_57_DOC)

    assert "Issue #59" in issue_doc
    assert "whole-repository text purge" in issue_doc or "whole-repository `python3` text purge" in issue_doc

    for bucket, paths in NONCRITICAL_PYTHON3_BUCKETS.items():
        assert bucket in issue_doc
        assert any(path.exists() and "python3" in _read(path) for path in paths), bucket

    for path in CONTRACT_CRITICAL_ACTIVE_PATHS:
        if not path.exists():
            continue
        text = _read(path)
        assert "python3 -m pytest" not in text, str(path)
        assert "source .venv/bin/activate" not in text, str(path)


def test_run_sdlc_tests_help_guides_formal_checks_to_controlled_entries():
    runner = _read(RUN_SDLC_TESTS)

    assert "bash scripts/dev_python.sh -m pytest" in runner
    assert "bash preflight.sh --report-all" in runner
    assert "--all" in runner
    assert "--cuj <N>" in runner
    assert "-h, --help" in runner
    assert 'scripts/test_cuj_${cuj_num}_mock.sh' in runner
    assert "source .venv/bin/activate" not in runner
    assert "python3 -m pytest" not in runner
