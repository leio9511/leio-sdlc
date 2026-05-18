from pathlib import Path
import os
import socket
import subprocess
import urllib.request

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
DEV_WRAPPER_PATH = REPO_ROOT / "scripts" / "dev_python.sh"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
REQUIRED_WORKFLOW_NAME = "Preflight"
DEFAULT_PREFLIGHT_COMMAND = "bash preflight.sh"
REPORT_ALL_PREFLIGHT_COMMAND = "bash preflight.sh --report-all"
LEGACY_REPORT_ALL_PREFLIGHT_COMMAND = "PATH=\"${PWD}/.venv/bin:${PATH}\" bash preflight.sh --report-all"
RUNTIME_SMOKE_SCRIPT = "scripts/runtime_smoke.py"
REQUIRED_TRIGGER_KEYS = {"push", "pull_request"}
REQUIRED_STEP_IDS = {
    "checkout",
    "python-runtime-setup",
    "node-runtime-setup",
    "minimal-bootstrap",
    "run-preflight",
    "run-runtime-smoke",
}
CONTROLLED_INTERPRETER_MARKERS = ("scripts/dev_python.sh", ".venv/bin/python")
PREFLIGHT_CONTRACT_CRITICAL_DESCRIPTIONS = (
    "ignore-manifest parsing",
    "pytest execution",
    "script-level Python tests",
    "syntax checks",
)


DEPENDENCY_LIST_MARKERS = (
    "pip install pytest PyYAML",
    "pip install PyYAML pytest",
    "python -m pip install pytest PyYAML",
    "python -m pip install PyYAML pytest",
)
FAILURE_MASKING_MARKERS = ("|| true", "continue-on-error")
MANUAL_ACTIVATION_MARKERS = (
    "source .venv/bin/activate",
    ". .venv/bin/activate",
    "source ${REPO_ROOT}/.venv/bin/activate",
)


def _load_workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert isinstance(workflow, dict), "Workflow YAML must parse into a mapping."
    return workflow


def _get_preflight_job():
    workflow = _load_workflow()
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "Workflow must define jobs as a mapping."

    preflight_job = jobs.get("preflight")
    assert isinstance(preflight_job, dict), "Workflow must define a preflight job."
    return preflight_job


def _get_steps_by_id():
    preflight_job = _get_preflight_job()
    steps = preflight_job.get("steps")
    assert isinstance(steps, list), "Preflight job must define steps as a list."

    steps_by_id = {}
    for step in steps:
        assert isinstance(step, dict), "Each workflow step must be a mapping."
        step_id = step.get("id")
        if step_id:
            steps_by_id[step_id] = step
    return steps_by_id


def _assert_no_continue_on_error(value):
    if isinstance(value, dict):
        assert "continue-on-error" not in value, (
            "Workflow must not use continue-on-error in the preflight job."
        )
        for nested_value in value.values():
            _assert_no_continue_on_error(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_no_continue_on_error(nested_value)


def _workflow_text():
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _wrapper_text():
    assert DEV_WRAPPER_PATH.is_file(), "Expected scripts/dev_python.sh to exist."
    return DEV_WRAPPER_PATH.read_text(encoding="utf-8")


def _preflight_text():
    return (REPO_ROOT / "preflight.sh").read_text(encoding="utf-8")


def _assert_required_runtime_smoke_command(run_command):
    assert RUNTIME_SMOKE_SCRIPT in run_command
    assert "scripts/runtime_python.sh" in run_command
    assert "RUNNER_TEMP" in run_command
    assert "requirements.txt" in run_command
    assert any(marker in run_command for marker in CONTROLLED_INTERPRETER_MARKERS)
    assert "python3 scripts/runtime_smoke.py" not in run_command
    assert "--expected-runtime-python" not in run_command


def _assert_contract_critical_preflight_paths_use_controlled_interpreter(preflight_text):
    assert "DEV_PYTHON=\"$PROJECT_DIR/scripts/dev_python.sh\"" in preflight_text
    assert 'PYTHON_CMD=("$DEV_PYTHON")' in preflight_text
    assert '"${PYTHON_CMD[@]}" - "$IGNORE_MANIFEST"' in preflight_text
    assert '"${PYTHON_CMD[@]}" -m pytest tests/test_template_compliance.py' in preflight_text
    assert '"${PYTHON_CMD[@]}" -m pytest tests/' in preflight_text
    assert '"${PYTHON_CMD[@]}" "$f"' in preflight_text
    assert '"${PYTHON_CMD[@]}" -m py_compile scripts/agent_driver.py' in preflight_text

    forbidden_contract_critical_invocations = (
        "python3 - \"$IGNORE_MANIFEST\"",
        "run_test \"pytest tests/test_template_compliance.py\"",
        "run_test_argv \"Pytest functional & unittest suite\" pytest tests/",
        "run_test \"python3 $f\"",
        "python3 -m py_compile scripts/agent_driver.py",
    )
    for invocation in forbidden_contract_critical_invocations:
        assert invocation not in preflight_text


def test_preflight_workflow_exists_at_required_path():
    assert WORKFLOW_PATH.is_file(), (
        "Expected repository workflow at .github/workflows/preflight.yml."
    )


def test_preflight_workflow_declares_required_triggers_and_step_inventory():
    workflow = _load_workflow()
    trigger_block = workflow.get("on")
    assert isinstance(trigger_block, dict), "Workflow must define an 'on' mapping."
    assert workflow.get("name") == REQUIRED_WORKFLOW_NAME
    assert REQUIRED_TRIGGER_KEYS.issubset(trigger_block.keys())

    preflight_job = _get_preflight_job()
    assert preflight_job.get("runs-on") == "ubuntu-latest"

    steps_by_id = _get_steps_by_id()
    assert REQUIRED_STEP_IDS.issubset(steps_by_id.keys())


def test_preflight_workflow_uses_report_all_gate_command():
    run_preflight_step = _get_steps_by_id()["run-preflight"]
    assert run_preflight_step.get("run", "").strip() == REPORT_ALL_PREFLIGHT_COMMAND


def test_github_preflight_runs_standard_preflight_after_controlled_bootstrap():
    steps_by_id = _get_steps_by_id()
    bootstrap_run = steps_by_id["minimal-bootstrap"].get("run", "")
    preflight_run = steps_by_id["run-preflight"].get("run", "").strip()

    assert "scripts/dev_python.sh" in bootstrap_run
    assert preflight_run == REPORT_ALL_PREFLIGHT_COMMAND
    assert LEGACY_REPORT_ALL_PREFLIGHT_COMMAND != preflight_run


def test_github_preflight_runs_official_runtime_smoke_with_controlled_interpreter():
    runtime_smoke_step = _get_steps_by_id()["run-runtime-smoke"]
    _assert_required_runtime_smoke_command(runtime_smoke_step.get("run", ""))


def test_preflight_contract_critical_python_paths_use_controlled_interpreter():
    preflight_text = _preflight_text()
    for description in PREFLIGHT_CONTRACT_CRITICAL_DESCRIPTIONS:
        assert description
    _assert_contract_critical_preflight_paths_use_controlled_interpreter(preflight_text)


def test_runtime_smoke_step_preserves_truthful_failure_semantics():
    preflight_job = _get_preflight_job()
    runtime_smoke_step = _get_steps_by_id()["run-runtime-smoke"]
    _assert_no_continue_on_error(preflight_job)
    assert "|| true" not in runtime_smoke_step.get("run", "")
    _assert_required_runtime_smoke_command(runtime_smoke_step.get("run", ""))


def test_preflight_workflow_preserves_truthful_failure_semantics_in_report_all_mode():
    preflight_job = _get_preflight_job()
    _assert_no_continue_on_error(preflight_job)

    for step in preflight_job.get("steps", []):
        run_command = step.get("run")
        if isinstance(run_command, str):
            assert "|| true" not in run_command
            assert DEFAULT_PREFLIGHT_COMMAND in run_command or REPORT_ALL_PREFLIGHT_COMMAND in run_command or step.get("id") != "run-preflight"

    run_preflight_step = _get_steps_by_id()["run-preflight"]
    assert run_preflight_step.get("run", "").strip() == REPORT_ALL_PREFLIGHT_COMMAND


def test_preflight_workflow_contract_is_locally_verifiable_from_repository_data(monkeypatch):
    def _forbid(*args, **kwargs):
        raise AssertionError("Workflow contract verification must stay repository-local.")

    monkeypatch.setattr(subprocess, "run", _forbid)
    monkeypatch.setattr(subprocess, "Popen", _forbid)
    monkeypatch.setattr(os, "system", _forbid)
    monkeypatch.setattr(socket, "create_connection", _forbid)
    monkeypatch.setattr(urllib.request, "urlopen", _forbid)

    workflow = _load_workflow()
    steps_by_id = _get_steps_by_id()

    assert workflow["name"] == REQUIRED_WORKFLOW_NAME
    assert REQUIRED_TRIGGER_KEYS.issubset(workflow["on"].keys())
    assert REQUIRED_STEP_IDS.issubset(steps_by_id.keys())
    assert steps_by_id["run-preflight"]["run"].strip() == REPORT_ALL_PREFLIGHT_COMMAND
    _assert_required_runtime_smoke_command(steps_by_id["run-runtime-smoke"].get("run", ""))


def test_github_preflight_bootstraps_python_from_requirements_via_dev_wrapper():
    assert REQUIREMENTS_PATH.is_file(), "Root requirements.txt must be the dependency entry."
    workflow_text = _workflow_text()
    wrapper_text = _wrapper_text()
    bootstrap_run = _get_steps_by_id()["minimal-bootstrap"].get("run", "")

    assert "scripts/dev_python.sh" in bootstrap_run
    assert "requirements.txt" in workflow_text
    assert "pip install -r requirements.txt" in workflow_text
    assert "requirements.txt" in wrapper_text
    assert "pip install -r" in wrapper_text
    assert ".venv" in wrapper_text
    assert ".venv/bin/python" in wrapper_text

    combined_contract_text = workflow_text + "\n" + wrapper_text
    for marker in DEPENDENCY_LIST_MARKERS:
        assert marker not in combined_contract_text


def test_github_preflight_keeps_required_runtime_setup_and_triggers():
    workflow = _load_workflow()
    steps_by_id = _get_steps_by_id()

    assert workflow["name"] == REQUIRED_WORKFLOW_NAME
    assert REQUIRED_TRIGGER_KEYS.issubset(workflow["on"].keys())
    assert steps_by_id["checkout"].get("uses") == "actions/checkout@v4"
    assert steps_by_id["python-runtime-setup"].get("uses") == "actions/setup-python@v5"
    assert steps_by_id["node-runtime-setup"].get("uses") == "actions/setup-node@v4"
    assert "scripts/dev_python.sh" in steps_by_id["minimal-bootstrap"].get("run", "")


def test_ci_contract_does_not_require_manual_venv_activation():
    workflow_text = _workflow_text()
    combined_contract_text = workflow_text + "\n" + _wrapper_text()

    for marker in MANUAL_ACTIVATION_MARKERS:
        assert marker not in combined_contract_text

    assert ".venv/bin/python" in combined_contract_text
    assert "scripts/dev_python.sh" in workflow_text
    assert LEGACY_REPORT_ALL_PREFLIGHT_COMMAND != _get_steps_by_id()["run-preflight"].get("run", "").strip()
    assert _get_steps_by_id()["run-preflight"].get("run", "").strip() == REPORT_ALL_PREFLIGHT_COMMAND


def test_github_preflight_bootstrap_has_truthful_failure_semantics():
    workflow_text = _workflow_text()
    wrapper_text = _wrapper_text()
    preflight_job = _get_preflight_job()

    _assert_no_continue_on_error(preflight_job)
    for marker in FAILURE_MASKING_MARKERS:
        assert marker not in workflow_text
        assert marker not in wrapper_text
