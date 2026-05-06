from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
GATE_COMMAND = "bash preflight.sh"


def load_workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as workflow_file:
        return yaml.safe_load(workflow_file)


def workflow_on(workflow):
    # Older YAML 1.1 parsers may resolve the unquoted key "on" as boolean True.
    return workflow.get("on", workflow.get(True, {}))


def preflight_job(workflow):
    jobs = workflow.get("jobs", {})
    assert "preflight" in jobs
    return jobs["preflight"]


def all_steps(workflow):
    steps = []
    for job in workflow.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


def gate_steps(workflow):
    return [step for step in all_steps(workflow) if step.get("run") == GATE_COMMAND]


def test_preflight_workflow_file_exists_at_required_path():
    assert WORKFLOW_PATH.exists()
    workflow = load_workflow()
    assert isinstance(workflow, dict)
    assert workflow.get("name") == "Preflight"


def test_preflight_workflow_declares_push_and_pull_request_triggers():
    workflow = load_workflow()
    triggers = workflow_on(workflow)

    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers


def test_preflight_job_runs_on_github_hosted_clean_runner():
    workflow = load_workflow()
    job = preflight_job(workflow)
    runs_on = job.get("runs-on")

    runner_labels = runs_on if isinstance(runs_on, list) else [runs_on]
    assert any(isinstance(label, str) and label.startswith("ubuntu-") for label in runner_labels)
    assert "self-hosted" not in runner_labels


def test_preflight_workflow_executes_real_gate_command_once():
    workflow = load_workflow()
    steps = all_steps(workflow)

    assert sum(1 for step in steps if step.get("uses", "").startswith("actions/checkout")) >= 1
    assert len(gate_steps(workflow)) == 1

    run_commands = [step.get("run") for step in steps if "run" in step]
    assert run_commands == [GATE_COMMAND]


def test_preflight_workflow_does_not_mask_gate_failures():
    workflow = load_workflow()
    jobs = workflow.get("jobs", {})
    steps = all_steps(workflow)

    assert all("continue-on-error" not in job for job in jobs.values())
    assert all("continue-on-error" not in step for step in steps)

    gate_step = gate_steps(workflow)[0]
    gate_run = gate_step["run"]
    prohibited_fragments = [
        "|| true",
        "exit 0",
        "if ",
        "fi",
        "set +e",
    ]
    assert all(fragment not in gate_run for fragment in prohibited_fragments)
