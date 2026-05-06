from pathlib import Path

import pytest
import yaml


WORKFLOW_PATH = Path(".github/workflows/preflight.yml")
REQUIRED_STEP_NAMES = {
    "checkout",
    "python-runtime-setup",
    "node-runtime-setup",
    "minimal-bootstrap",
    "bash preflight.sh",
}


def _load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _workflow_triggers(workflow):
    return workflow.get("on") or workflow.get(True) or {}


def _preflight_job_steps(workflow):
    jobs = workflow.get("jobs") or {}
    for job in jobs.values():
        steps = job.get("steps") or []
        if any(step.get("run", "").strip() == "bash preflight.sh" for step in steps):
            return steps
    pytest.fail("No workflow job executes the authoritative gate command 'bash preflight.sh'.")


def _step_named(steps, name):
    for step in steps:
        if step.get("name") == name:
            return step
    pytest.fail(f"Workflow is missing required step '{name}'.")


def test_preflight_workflow_exists_at_required_path():
    assert WORKFLOW_PATH.is_file()


def test_preflight_workflow_declares_push_and_pull_request_triggers():
    workflow = _load_workflow()

    triggers = _workflow_triggers(workflow)

    assert "push" in triggers
    assert "pull_request" in triggers


def test_preflight_workflow_uses_required_runtime_setup_and_real_gate_command():
    workflow = _load_workflow()
    steps = _preflight_job_steps(workflow)

    step_names = {step.get("name") for step in steps}
    assert REQUIRED_STEP_NAMES.issubset(step_names)

    checkout_step = _step_named(steps, "checkout")
    assert checkout_step.get("uses", "").startswith("actions/checkout@")

    python_step = _step_named(steps, "python-runtime-setup")
    assert python_step.get("uses", "").startswith("actions/setup-python@")

    node_step = _step_named(steps, "node-runtime-setup")
    assert node_step.get("uses", "").startswith("actions/setup-node@")

    bootstrap_step = _step_named(steps, "minimal-bootstrap")
    assert bootstrap_step.get("run", "").strip()

    gate_step = _step_named(steps, "bash preflight.sh")
    assert gate_step.get("run", "").strip() == "bash preflight.sh"


def test_preflight_workflow_separates_minimal_bootstrap_from_the_authoritative_gate_step():
    workflow = _load_workflow()
    steps = _preflight_job_steps(workflow)

    bootstrap_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "minimal-bootstrap"
    )
    gate_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "bash preflight.sh"
    )

    bootstrap_step = steps[bootstrap_index]
    gate_step = steps[gate_index]

    assert bootstrap_index < gate_index
    assert bootstrap_step is not gate_step
    assert "bash preflight.sh" not in bootstrap_step.get("run", "")
    assert gate_step.get("run", "").strip() == "bash preflight.sh"
