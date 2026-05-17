from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUE_DOC = REPO_ROOT / "docs" / "Issue_57_Python_Execution_Contract.md"
README = REPO_ROOT / "README.md"
SKILL = REPO_ROOT / "SKILL.md"

REQUIRED_DEPENDENCY_ENTRY = (
    "requirements.txt at the repository root, currently serving runtime, "
    "development, and test dependencies together"
)
REQUIRED_DEV_CONTEXT = "repository-root .venv"
REQUIRED_RUNTIME_CONTEXT = (
    "deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap"
)
REQUIRED_SCOPE = "leio-sdlc local development, testing, deployed runtime execution, and GitHub CI only"
REQUIRED_SMOKE_POLICY = (
    "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, "
    "and startup-path initialization. Do not use full auditor/orchestrator/long-running business "
    "execution as default smoke validation."
)
REQUIRED_CORE_GOAL = (
    "Define a controlled, repeatable Python execution contract for local development, testing, "
    "deployed skill runtime, and GitHub CI without depending on unmanaged system Python state."
)


def _read(path):
    return path.read_text(encoding="utf-8")


def test_official_issue_57_doc_states_unique_dependency_and_scope():
    doc = _read(ISSUE_DOC)

    assert REQUIRED_DEPENDENCY_ENTRY in doc
    assert REQUIRED_SCOPE in doc
    assert REQUIRED_CORE_GOAL in doc
    assert REQUIRED_SMOKE_POLICY in doc
    assert "ClawHub installation" in doc
    assert "public packaging/distribution contract" in doc
    assert "cross-skill global runtime unification" in doc


def test_readme_documents_controlled_dev_execution_without_manual_activation_contract():
    readme = _read(README)

    assert REQUIRED_DEPENDENCY_ENTRY in readme
    assert REQUIRED_DEV_CONTEXT in readme
    assert "scripts/dev_python.sh" in readme
    assert "bash preflight.sh --report-all" in readme
    assert "source .venv/bin/activate" not in readme
    assert "python3 -m pytest" not in readme


def test_readme_documents_deployed_runtime_and_shared_smoke_contract():
    readme = _read(README)

    assert REQUIRED_RUNTIME_CONTEXT in readme
    assert "scripts/runtime_smoke.py" in readme
    assert "deploy/runtime and CI" in readme
    assert REQUIRED_SMOKE_POLICY in readme


def test_skill_examples_use_controlled_runtime_interpreter_for_orchestrator_commands():
    skill = _read(SKILL)
    active_skill = re.sub(r"```.*?```", "", skill, flags=re.DOTALL)

    assert "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python" in skill
    assert "scripts/orchestrator.py" in skill
    assert "python3 \"${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}\"/leio-sdlc/scripts/orchestrator.py" not in skill
    assert "python3 ${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/orchestrator.py" not in skill
    assert "python3" not in active_skill


def test_documentation_distinguishes_dev_and_runtime_contexts():
    doc = _read(ISSUE_DOC)

    assert REQUIRED_DEV_CONTEXT in doc
    assert REQUIRED_RUNTIME_CONTEXT in doc
    assert "development/test execution context" in doc
    assert "deployed runtime execution context" in doc
    assert "not a global shared Python environment" in doc
    assert "other skills" in doc
