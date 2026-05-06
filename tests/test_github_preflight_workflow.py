from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "ci" / "preflight-soft-gate.md"
GATE_COMMAND = "bash preflight.sh"
GITHUB_DISCOVERY_WORKFLOW_NAME = "Preflight"
GITHUB_DISCOVERY_WORKFLOW_FILENAME = "preflight.yml"
SOFT_GATE_SEMANTICS_STATEMENT = (
    "Phase 2 soft gate means the GitHub Actions result is visible and truthful, "
    "but not yet configured as a required merge blocker."
)
MASKING_PROHIBITION_STATEMENT = (
    "Do not use continue-on-error or any equivalent masking mechanism to convert a real "
    "preflight failure into a successful CI result."
)
LOCAL_CONTRACT_TEST_EXPECTATION = (
    "The primary correctness checks for this phase must be implemented as "
    "repository-local automated contract tests against .github/workflows/preflight.yml "
    "rather than as live GitHub-only verification."
)
SUCCESS_FAILURE_MAPPING = """bash preflight.sh exit 0 -> CI job success
bash preflight.sh non-zero exit -> CI job failure"""
REQUIRED_STEP_IDS = [
    "checkout",
    "python-runtime-setup",
    "node-runtime-setup",
    "minimal-bootstrap",
]
TRIGGER_FILTER_KEYS = {
    "branches",
    "branches-ignore",
    "paths",
    "paths-ignore",
    "tags",
    "tags-ignore",
}


def load_workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as workflow_file:
        return yaml.safe_load(workflow_file)


def load_runbook():
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def workflow_on(workflow):
    # Older YAML 1.1 parsers may resolve the unquoted key "on" as boolean True.
    return workflow.get("on", workflow.get(True, {}))


def preflight_job(workflow):
    jobs = workflow.get("jobs", {})
    assert "preflight" in jobs
    return jobs["preflight"]


def preflight_steps(workflow):
    steps = preflight_job(workflow).get("steps", [])
    assert steps
    return steps


def all_steps(workflow):
    steps = []
    for job in workflow.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


def step_ids(workflow):
    return [step.get("id") for step in preflight_steps(workflow)]


def step_by_id(workflow, step_id):
    matches = [step for step in preflight_steps(workflow) if step.get("id") == step_id]
    assert len(matches) == 1
    return matches[0]


def gate_steps(workflow):
    return [step for step in all_steps(workflow) if step.get("run") == GATE_COMMAND]


def assert_no_masking(run_command):
    prohibited_fragments = [
        "|| true",
        "exit 0",
        "set +e",
    ]
    assert all(fragment not in run_command for fragment in prohibited_fragments)


def test_preflight_soft_gate_runbook_exists():
    assert RUNBOOK_PATH.exists()
    assert RUNBOOK_PATH.is_file()
    assert RUNBOOK_PATH.is_relative_to(REPO_ROOT)

    runbook = load_runbook()
    forbidden_live_dependency_terms = [
        "api.github.com",
        "gh api",
        "curl",
        "requests.get",
    ]

    assert str(RUNBOOK_PATH.relative_to(REPO_ROOT)) == "docs/ci/preflight-soft-gate.md"
    assert all(term not in runbook for term in forbidden_live_dependency_terms)


def test_preflight_soft_gate_runbook_preserves_required_statements():
    runbook = load_runbook()

    assert ".github/workflows/preflight.yml" in runbook
    assert GATE_COMMAND in runbook
    assert SOFT_GATE_SEMANTICS_STATEMENT in runbook
    assert MASKING_PROHIBITION_STATEMENT in runbook
    assert LOCAL_CONTRACT_TEST_EXPECTATION in runbook
    assert SUCCESS_FAILURE_MAPPING in runbook


def test_preflight_soft_gate_runbook_defines_low_frequency_external_witness():
    runbook = load_runbook().lower()

    assert "low-frequency external witness" in runbook
    assert "push" in runbook
    assert "pull_request" in runbook
    assert "preflight" in runbook
    assert "terminal result" in runbook
    assert "success" in runbook
    assert "failure" in runbook
    assert "not as the primary local coder-loop validation" in runbook
    assert "must not require network access" in runbook


def test_preflight_workflow_documents_soft_gate_as_truthful_non_required_status():
    runbook = load_runbook()

    assert SOFT_GATE_SEMANTICS_STATEMENT in runbook


def test_preflight_workflow_file_exists_at_required_path():
    assert WORKFLOW_PATH.exists()
    workflow = load_workflow()
    assert isinstance(workflow, dict)
    assert workflow.get("name") == GITHUB_DISCOVERY_WORKFLOW_NAME


def test_preflight_workflow_uses_expected_pre_publish_discovery_identifiers():
    # This is a local pre-publish guard only; remote discovery is verified with
    # GitHub Actions inspection after the workflow exists on a remote ref.
    workflow = load_workflow()

    assert WORKFLOW_PATH.name == GITHUB_DISCOVERY_WORKFLOW_FILENAME
    assert str(WORKFLOW_PATH.relative_to(REPO_ROOT)) == ".github/workflows/preflight.yml"
    assert workflow.get("name") == GITHUB_DISCOVERY_WORKFLOW_NAME
    assert workflow.get("name", "").strip() == GITHUB_DISCOVERY_WORKFLOW_NAME


def test_preflight_workflow_run_name_exposes_run_selection_identity():
    workflow = load_workflow()

    assert workflow.get("run-name") == (
        "Preflight ${{ github.event_name }} ${{ github.ref_name }} ${{ github.sha }}"
    )


def test_preflight_workflow_declares_push_and_pull_request_triggers():
    workflow = load_workflow()
    triggers = workflow_on(workflow)

    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers


def test_preflight_workflow_triggers_are_unfiltered_for_published_refs():
    workflow = load_workflow()
    triggers = workflow_on(workflow)

    for required_event in ("push", "pull_request"):
        event_config = triggers[required_event]
        if event_config is None:
            event_config = {}
        assert isinstance(event_config, dict)
        assert TRIGGER_FILTER_KEYS.isdisjoint(event_config)


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
    assert run_commands[-1] == GATE_COMMAND
    assert run_commands.count(GATE_COMMAND) == 1


def test_preflight_workflow_does_not_mask_gate_failures():
    workflow = load_workflow()
    jobs = workflow.get("jobs", {})
    steps = all_steps(workflow)

    assert all("continue-on-error" not in job for job in jobs.values())
    assert all("continue-on-error" not in step for step in steps)

    gate_step = gate_steps(workflow)[0]
    gate_run = gate_step["run"]
    assert_no_masking(gate_run)
    assert "if " not in gate_run
    assert "fi" not in gate_run


def test_preflight_workflow_contains_required_runtime_and_bootstrap_steps():
    workflow = load_workflow()
    ids = step_ids(workflow)

    for required_step_id in REQUIRED_STEP_IDS:
        assert required_step_id in ids
    assert len(gate_steps(workflow)) == 1


def test_preflight_workflow_orders_bootstrap_before_real_gate():
    workflow = load_workflow()
    steps = preflight_steps(workflow)
    ids = step_ids(workflow)
    gate_index = next(index for index, step in enumerate(steps) if step.get("run") == GATE_COMMAND)

    checkout_index = ids.index("checkout")
    python_index = ids.index("python-runtime-setup")
    node_index = ids.index("node-runtime-setup")
    bootstrap_index = ids.index("minimal-bootstrap")

    assert checkout_index < python_index
    assert checkout_index < node_index
    assert python_index < bootstrap_index
    assert node_index < bootstrap_index
    assert bootstrap_index < gate_index


def test_preflight_workflow_uses_supported_setup_actions():
    workflow = load_workflow()

    checkout = step_by_id(workflow, "checkout")
    python_setup = step_by_id(workflow, "python-runtime-setup")
    node_setup = step_by_id(workflow, "node-runtime-setup")

    assert checkout.get("uses", "").startswith("actions/checkout@")
    assert python_setup.get("uses", "").startswith("actions/setup-python@")
    assert python_setup.get("with", {}).get("python-version", "").startswith("3.")
    assert node_setup.get("uses", "").startswith("actions/setup-node@")
    assert node_setup.get("with", {}).get("node-version") in {"20", "22"}


def test_minimal_bootstrap_does_not_replace_preflight_gate():
    workflow = load_workflow()
    bootstrap = step_by_id(workflow, "minimal-bootstrap")
    bootstrap_run = bootstrap.get("run", "")
    forbidden_bootstrap_fragments = [
        "pytest",
        "preflight.sh",
        "scripts/test_",
        "for f in",
        "npm test",
        "python3 scripts/test_",
        "bash scripts/test_",
    ]

    assert bootstrap_run
    assert all(fragment not in bootstrap_run for fragment in forbidden_bootstrap_fragments)
    assert len(gate_steps(workflow)) == 1
    assert gate_steps(workflow)[0] == preflight_steps(workflow)[-1]


def test_preflight_workflow_does_not_mask_failures_after_bootstrap_hardening():
    workflow = load_workflow()
    jobs = workflow.get("jobs", {})

    assert all("continue-on-error" not in job for job in jobs.values())
    for step in all_steps(workflow):
        assert "continue-on-error" not in step
        if "run" in step:
            assert_no_masking(step["run"])
