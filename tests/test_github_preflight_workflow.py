from pathlib import Path
import os
import socket
import subprocess
import urllib.request

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
REQUIRED_TRIGGER_KEYS = {"push", "pull_request"}
REQUIRED_STEP_IDS = {
    "checkout",
    "python-runtime-setup",
    "node-runtime-setup",
    "minimal-bootstrap",
    "run-preflight",
}


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


def test_preflight_workflow_exists_at_required_path():
    assert WORKFLOW_PATH.is_file(), (
        "Expected repository workflow at .github/workflows/preflight.yml."
    )


def test_preflight_workflow_declares_required_triggers_and_step_inventory():
    workflow = _load_workflow()
    trigger_block = workflow.get("on")
    assert isinstance(trigger_block, dict), "Workflow must define an 'on' mapping."
    assert REQUIRED_TRIGGER_KEYS.issubset(trigger_block.keys())

    preflight_job = _get_preflight_job()
    assert preflight_job.get("runs-on") == "ubuntu-latest"

    steps_by_id = _get_steps_by_id()
    assert REQUIRED_STEP_IDS.issubset(steps_by_id.keys())


def test_preflight_workflow_uses_real_gate_command():
    run_preflight_step = _get_steps_by_id()["run-preflight"]
    assert run_preflight_step.get("run", "").strip() == "bash preflight.sh --report-all"


def test_preflight_workflow_preserves_truthful_failure_semantics():
    preflight_job = _get_preflight_job()
    _assert_no_continue_on_error(preflight_job)

    for step in preflight_job.get("steps", []):
        run_command = step.get("run")
        if isinstance(run_command, str):
            assert "|| true" not in run_command

    run_preflight_step = _get_steps_by_id()["run-preflight"]
    assert run_preflight_step.get("run", "").strip() == "bash preflight.sh --report-all"


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

    assert REQUIRED_TRIGGER_KEYS.issubset(workflow["on"].keys())
    assert REQUIRED_STEP_IDS.issubset(steps_by_id.keys())
    assert steps_by_id["run-preflight"]["run"].strip() == "bash preflight.sh --report-all"
