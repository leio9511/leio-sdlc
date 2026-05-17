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


def test_dev_python_wrapper_uses_repo_venv_and_root_requirements_without_manual_activation():
    wrapper = _read(DEV_PYTHON)

    assert 'REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in wrapper
    assert 'VENV_DIR="${REPO_ROOT}/.venv"' in wrapper
    assert 'PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"' in wrapper
    assert 'REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"' in wrapper
    assert 'python3 -m venv "${VENV_DIR}"' in wrapper
    assert '"${PYTHON_BIN}" -m pip install -r "${REQUIREMENTS_FILE}"' in wrapper
    assert 'exec "${PYTHON_BIN}" "$@"' in wrapper
    assert "source .venv/bin/activate" not in wrapper


def test_preflight_routes_python_checks_through_dev_wrapper_under_normal_operation():
    preflight = _read(PREFLIGHT)

    assert 'DEV_PYTHON="$PROJECT_DIR/scripts/dev_python.sh"' in preflight
    assert 'PYTHON_CMD=("$DEV_PYTHON")' in preflight
    assert 'run_test_argv "Template Compliance Gate" "${PYTHON_CMD[@]}" -m pytest' in preflight
    assert 'run_test_argv "Pytest functional & unittest suite" "${PYTHON_CMD[@]}" -m pytest tests/' in preflight
    assert 'run_test_argv "Python Test: $f" "${PYTHON_CMD[@]}" "$f"' in preflight
    assert 'run_test_argv "Syntax Check: agent_driver.py" "${PYTHON_CMD[@]}" -m py_compile scripts/agent_driver.py' in preflight

    fallback_index = preflight.find('PYTHON_CMD=("python3")')
    assert fallback_index != -1
    fallback_context = preflight[max(0, fallback_index - 240): fallback_index + 160]
    assert 'SDLC_TEST_MODE' in fallback_context
    assert 'test-only fallback' in fallback_context.lower()


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
