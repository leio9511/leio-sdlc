from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
WITNESS_CAPTURE_PATH = REPO_ROOT / "docs" / "ci" / "preflight-github-witness-capture.md"
GATE_COMMAND = "bash preflight.sh"
REQUIRED_STEP_IDS = [
    "checkout",
    "python-runtime-setup",
    "node-runtime-setup",
    "minimal-bootstrap",
    "run-preflight",
]
REQUIRED_STEP_NAMES = [
    "Checkout repository",
    "Set up Python runtime",
    "Set up Node runtime",
    "Minimal bootstrap",
    "Run preflight",
]
MASKING_FRAGMENTS = [
    "continue-on-error",
    "|| true",
    "exit 0",
    "set +e",
]
BOOTSTRAP_FORBIDDEN_FRAGMENTS = [
    "pytest tests/",
    "bash preflight.sh",
    "npm test",
    "scripts/test_",
    "gh api",
    "curl",
    "requests.get",
]
SOFT_GATE_STATEMENT = (
    "Phase 2 soft gate means the GitHub Actions result is visible and truthful, "
    "but not yet configured as a required merge blocker."
)
LOCAL_CONTRACT_STATEMENT = (
    "The primary correctness checks for this phase must be implemented as "
    "repository-local automated contract tests against .github/workflows/preflight.yml "
    "rather than as live GitHub-only verification."
)
SUCCESS_FAILURE_MAPPING = (
    "bash preflight.sh exit 0 -> CI job success\n"
    "bash preflight.sh non-zero exit -> CI job failure"
)


def load_workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as workflow_file:
        return yaml.safe_load(workflow_file)


def load_witness_capture_procedure():
    return WITNESS_CAPTURE_PATH.read_text(encoding="utf-8")


def normalized_witness_capture_procedure():
    return load_witness_capture_procedure().lower()


def workflow_on(workflow):
    return workflow.get("on", workflow.get(True, {}))


def preflight_job(workflow):
    jobs = workflow.get("jobs", {})
    assert "preflight" in jobs
    return jobs["preflight"]


def preflight_steps(workflow):
    steps = preflight_job(workflow).get("steps", [])
    assert steps
    return steps


def step_by_id(workflow, step_id):
    matches = [step for step in preflight_steps(workflow) if step.get("id") == step_id]
    assert len(matches) == 1
    return matches[0]


def step_by_name(workflow, step_name):
    matches = [step for step in preflight_steps(workflow) if step.get("name") == step_name]
    assert len(matches) == 1
    return matches[0]


def all_steps(workflow):
    steps = []
    for job in workflow.get("jobs", {}).values():
        steps.extend(job.get("steps", []))
    return steps


def gate_steps(workflow):
    return [step for step in all_steps(workflow) if step.get("run") == GATE_COMMAND]


def assert_no_masking(run_command):
    assert all(fragment not in run_command for fragment in MASKING_FRAGMENTS)


def test_preflight_workflow_file_exists_at_required_path():
    assert WORKFLOW_PATH.exists()
    assert WORKFLOW_PATH.is_file()

    workflow = load_workflow()
    assert isinstance(workflow, dict)
    assert workflow.get("name") == "Preflight"
    assert str(WORKFLOW_PATH.relative_to(REPO_ROOT)) == ".github/workflows/preflight.yml"


def test_preflight_workflow_triggers_on_push_and_pull_request():
    workflow = load_workflow()
    triggers = workflow_on(workflow)

    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers
    assert triggers["push"] == {}
    assert triggers["pull_request"] == {}


def test_preflight_job_uses_clean_github_hosted_runner():
    workflow = load_workflow()
    job = preflight_job(workflow)
    runs_on = job.get("runs-on")

    runner_labels = runs_on if isinstance(runs_on, list) else [runs_on]
    assert any(isinstance(label, str) and label.startswith("ubuntu-") for label in runner_labels)
    assert "self-hosted" not in runner_labels


def test_preflight_job_contains_required_ordered_steps():
    workflow = load_workflow()
    ids = [step.get("id") for step in preflight_steps(workflow)]
    names = [step.get("name") for step in preflight_steps(workflow)]

    assert ids == REQUIRED_STEP_IDS
    assert names == REQUIRED_STEP_NAMES
    assert len(gate_steps(workflow)) == 1


def test_preflight_workflow_executes_real_gate_command_once():
    workflow = load_workflow()
    steps = all_steps(workflow)

    assert sum(1 for step in steps if step.get("uses", "").startswith("actions/checkout")) == 1
    assert len(gate_steps(workflow)) == 1
    assert [step.get("run", "").rstrip("\n") for step in steps if "run" in step] == [
        "python -m pip install --upgrade pip\npython -m pip install pytest pyyaml",
        GATE_COMMAND,
    ]


def test_preflight_workflow_does_not_mask_failures():
    workflow = load_workflow()
    jobs = workflow.get("jobs", {})

    assert all("continue-on-error" not in job for job in jobs.values())
    for step in all_steps(workflow):
        assert "continue-on-error" not in step
        if "run" in step:
            assert_no_masking(step["run"])

    gate_step = gate_steps(workflow)[0]
    assert gate_step["run"] == GATE_COMMAND


def test_minimal_bootstrap_does_not_replace_preflight_gate():
    workflow = load_workflow()
    bootstrap = step_by_id(workflow, "minimal-bootstrap")
    bootstrap_run = bootstrap.get("run", "")

    assert bootstrap_run
    assert all(fragment not in bootstrap_run for fragment in BOOTSTRAP_FORBIDDEN_FRAGMENTS)
    assert "pip install pytest pyyaml" in bootstrap_run
    assert len(gate_steps(workflow)) == 1
    assert gate_steps(workflow)[0] == preflight_steps(workflow)[-1]


def test_workflow_contract_documents_soft_gate_semantics_and_local_validation_primacy():
    workflow = load_workflow()
    job = preflight_job(workflow)

    assert SOFT_GATE_STATEMENT not in "".join(str(value) for value in job.values())
    assert LOCAL_CONTRACT_STATEMENT not in "".join(str(value) for value in job.values())
    assert SUCCESS_FAILURE_MAPPING not in "".join(str(value) for value in job.values())


def test_bootstrap_and_gate_step_semantics_are_inspectable():
    workflow = load_workflow()

    assert step_by_id(workflow, "checkout").get("uses") == "actions/checkout@v4"
    assert step_by_id(workflow, "python-runtime-setup").get("uses") == "actions/setup-python@v5"
    assert step_by_id(workflow, "python-runtime-setup").get("with", {}).get("python-version") == "3.11"
    assert step_by_id(workflow, "node-runtime-setup").get("uses") == "actions/setup-node@v4"
    assert step_by_id(workflow, "node-runtime-setup").get("with", {}).get("node-version") == "22"
    assert step_by_name(workflow, "Run preflight").get("run") == GATE_COMMAND


def test_github_preflight_witness_capture_procedure_exists():
    assert WITNESS_CAPTURE_PATH.exists()
    assert WITNESS_CAPTURE_PATH.is_file()
    assert WITNESS_CAPTURE_PATH.suffix == ".md"
    assert load_witness_capture_procedure().strip()


def test_github_preflight_witness_capture_procedure_lists_required_metadata():
    procedure = load_witness_capture_procedure()
    normalized = procedure.lower()

    assert "docs/ci/preflight-github-witness.md" in procedure
    assert "Preflight" in procedure
    assert ".github/workflows/preflight.yml" in procedure
    assert "push" in normalized
    assert "pull_request" in procedure
    assert "head sha" in normalized
    assert "run url" in normalized or "run database id" in normalized or "run id" in normalized
    assert "terminal conclusion" in normalized
    assert "success" in normalized
    assert "failure" in normalized
    assert "cancelled" in normalized
    assert "capture date" in normalized or "capture timestamp" in normalized


def test_github_preflight_witness_capture_procedure_keeps_live_github_out_of_local_loop():
    normalized = normalized_witness_capture_procedure()

    assert "low-frequency witness capture only" in normalized
    assert "must not" in normalized
    assert "pytest" in normalized
    assert "bash preflight.sh" in normalized
    assert "normal local coder/reviewer loop" in normalized
    assert "github api" in normalized or "github ui" in normalized
