from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "preflight.yml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
STANDARD_PREFLIGHT_COMMAND = "bash preflight.sh --report-all"
TRAP_PREFLIGHT_COMMAND = "bash preflight.sh --trap-mode --report-all"
FORBIDDEN_FAILURE_SWALLOWING_MARKERS = ("continue-on-error", "|| true", "set +e")
FORBIDDEN_AD_HOC_INSTALL_MARKERS = (
    "pip install pytest PyYAML",
    "pip install PyYAML pytest",
    "pip install pytest pyyaml",
    "pip install pyyaml pytest",
    "python -m pip install pytest PyYAML",
    "python -m pip install PyYAML pytest",
    "python -m pip install pytest pyyaml",
    "python -m pip install pyyaml pytest",
)


def _workflow():
    with WORKFLOW_PATH.open("r", encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    assert isinstance(parsed, dict), "Workflow YAML must parse into a mapping."
    return parsed


def _preflight_job():
    job = _workflow()["jobs"]["preflight"]
    assert isinstance(job, dict), "Preflight job must be a mapping."
    return job


def _steps():
    steps = _preflight_job()["steps"]
    assert isinstance(steps, list), "Preflight job steps must be a list."
    return steps


def _steps_by_id():
    return {step.get("id"): step for step in _steps() if step.get("id")}


def _step_index(step_id: str) -> int:
    for index, step in enumerate(_steps()):
        if step.get("id") == step_id:
            return index
    raise AssertionError(f"Missing workflow step id: {step_id}")


def _run(step_id: str) -> str:
    run = _steps_by_id()[step_id].get("run", "")
    assert isinstance(run, str), f"Workflow step {step_id} run block must be text."
    return run


def test_github_workflow_runs_standard_preflight_then_trap_preflight():
    steps_by_id = _steps_by_id()

    assert steps_by_id["run-preflight"].get("run", "").strip() == STANDARD_PREFLIGHT_COMMAND
    assert steps_by_id["run-trap-preflight"].get("run", "").strip() == TRAP_PREFLIGHT_COMMAND
    assert _step_index("run-preflight") < _step_index("run-trap-preflight")


def test_trap_preflight_ci_gate_has_truthful_failure_semantics():
    preflight_job = _preflight_job()
    standard_preflight_step = _steps_by_id()["run-preflight"]
    trap_preflight_step = _steps_by_id()["run-trap-preflight"]

    for marker in FORBIDDEN_FAILURE_SWALLOWING_MARKERS:
        assert marker not in str(preflight_job)
        assert marker not in _run("run-preflight")
        assert marker not in _run("run-trap-preflight")

    assert "continue-on-error" not in standard_preflight_step
    assert "continue-on-error" not in trap_preflight_step


def test_trap_preflight_ci_gate_reuses_controlled_bootstrap_dependencies():
    assert REQUIREMENTS_PATH.is_file(), "requirements.txt must remain the dependency entry."
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    bootstrap_run = _run("minimal-bootstrap")

    assert _step_index("minimal-bootstrap") < _step_index("run-preflight")
    assert _step_index("minimal-bootstrap") < _step_index("run-trap-preflight")
    assert "python -m venv .venv" in bootstrap_run
    assert ".venv/bin/python -m pip install -r requirements.txt" in bootstrap_run
    assert "bash scripts/dev_python.sh -m pip check" in bootstrap_run
    assert _run("run-preflight").strip() == STANDARD_PREFLIGHT_COMMAND
    assert _run("run-trap-preflight").strip() == TRAP_PREFLIGHT_COMMAND

    for marker in FORBIDDEN_AD_HOC_INSTALL_MARKERS:
        assert marker not in workflow_text
