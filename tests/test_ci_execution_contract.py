from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"

FORBIDDEN_DEPENDENCY_INSTALL_MARKERS = (
    "pip install pytest PyYAML",
    "pip install PyYAML pytest",
    "pip install pytest pyyaml",
    "pip install pyyaml pytest",
    "python -m pip install pytest PyYAML",
    "python -m pip install PyYAML pytest",
    "python -m pip install pytest pyyaml",
    "python -m pip install pyyaml pytest",
)

FAILURE_SWALLOWING_MARKERS = ("continue-on-error", "|| true")
FORMAL_AMBIENT_CHECK_MARKERS = (
    "python -m pytest",
    "python3 -m pytest",
    "pytest tests",
    "python scripts/runtime_smoke.py",
    "python3 scripts/runtime_smoke.py",
)
ALLOWED_BASE_PYTHON_BOOTSTRAP_MARKERS = (
    "python -m venv .venv",
    'python -m venv "${RUNTIME_SMOKE_ROOT}/.venv"',
)

TRAP_MODE_PREFLIGHT_COMMAND = "bash preflight.sh --trap-mode --report-all"
TRAP_REMEDIATION_BANNER = (
    "TRAP REMEDIATION PENDING",
    "This preflight run is green only under the temporary existing ignore-manifest rollout for trap-mode failures.",
    "Remaining trap failures must be burned down to zero before this issue is complete.",
)
TRAP_CLEAN_BANNER = (
    "TRAP MODE CLEAN",
    "Trap-mode preflight passed with no remaining trap remediation entries.",
)


def _workflow_text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    assert isinstance(parsed, dict)
    return parsed


def _preflight_steps():
    workflow = _workflow()
    steps = workflow["jobs"]["preflight"]["steps"]
    assert isinstance(steps, list)
    return steps


def _steps_by_id():
    return {step.get("id"): step for step in _preflight_steps() if step.get("id")}


def _step_run(step_id):
    run = _steps_by_id()[step_id].get("run", "")
    assert isinstance(run, str)
    return run


def test_workflow_installs_python_dependencies_from_requirements_only():
    assert REQUIREMENTS_PATH.is_file(), "requirements.txt must be the single dependency entry."
    workflow_text = _workflow_text()

    assert "requirements.txt" in workflow_text
    assert "pip install -r" in workflow_text
    assert "pytest" not in _step_run("minimal-bootstrap").replace("-m pytest", "")

    for marker in FORBIDDEN_DEPENDENCY_INSTALL_MARKERS:
        assert marker not in workflow_text


def test_workflow_uses_controlled_repo_venv_for_python_checks():
    workflow_text = _workflow_text()
    bootstrap_run = _step_run("minimal-bootstrap")
    preflight_run = _step_run("run-preflight").strip()
    runtime_run = _step_run("run-runtime-smoke")

    assert ".venv" in workflow_text
    assert "scripts/dev_python.sh" in bootstrap_run
    assert ".venv/bin/python" in bootstrap_run
    assert preflight_run == "bash preflight.sh --report-all"
    assert "scripts/runtime_python.sh" in runtime_run
    assert ".venv/bin/python" in runtime_run

    ambient_check_text = workflow_text
    for allowed_bootstrap in ALLOWED_BASE_PYTHON_BOOTSTRAP_MARKERS:
        ambient_check_text = ambient_check_text.replace(allowed_bootstrap, "")

    for marker in FORMAL_AMBIENT_CHECK_MARKERS:
        assert marker not in ambient_check_text


def test_workflow_reuses_standard_preflight_entry():
    assert _step_run("run-preflight").strip() == "bash preflight.sh --report-all"


def test_preflight_source_encodes_trap_mode_execution_contract():
    preflight_text = (REPO_ROOT / "preflight.sh").read_text(encoding="utf-8")
    manifest_text = (REPO_ROOT / "ignore_tests.json").read_text(encoding="utf-8")

    assert "--trap-mode" in preflight_text
    assert "TRAP_MODE=0" in preflight_text
    assert "activate_trap_mode" in preflight_text
    assert "mktemp -d" in preflight_text
    assert '"${PYTHON_CMD[@]}" -m venv "$TRAP_VENV_DIR"' in preflight_text
    assert 'cat > "$TRAP_VENV_DIR/bin/pytest"' in preflight_text
    assert 'export PATH="$TRAP_BIN_DIR:$TRAP_VENV_DIR/bin:$PREFLIGHT_BASE_PATH"' in preflight_text
    assert "rm -rf \"$TRAP_VENV_DIR\"" in preflight_text

    for line in TRAP_REMEDIATION_BANNER + TRAP_CLEAN_BANNER:
        assert line in preflight_text

    workflow_text = _workflow_text()
    assert TRAP_MODE_PREFLIGHT_COMMAND in workflow_text
    assert _step_run("run-preflight").strip() == "bash preflight.sh --report-all"
    assert _step_run("run-trap-preflight").strip() == TRAP_MODE_PREFLIGHT_COMMAND

    step_ids = [step.get("id") for step in _preflight_steps()]
    assert step_ids.index("run-preflight") < step_ids.index("run-trap-preflight")

    for repaired_target in (
        "scripts/test_escalation_clean.sh",
        "scripts/test_orchestrator_logs.sh",
        "scripts/test_orchestrator_session_strategy.sh",
    ):
        assert repaired_target not in manifest_text


def test_workflow_runs_execution_contract_smoke():
    runtime_step = _steps_by_id()["run-runtime-smoke"]
    runtime_run = runtime_step.get("run", "")
    workflow_text = _workflow_text()

    assert "runtime_smoke.py" in runtime_run
    assert "scripts/runtime_python.sh" in runtime_run
    assert "RUNNER_TEMP" in runtime_run
    assert "requirements.txt" in runtime_run
    assert "--expected-runtime-python" not in runtime_run

    for marker in FAILURE_SWALLOWING_MARKERS:
        assert marker not in workflow_text
        assert marker not in runtime_step
