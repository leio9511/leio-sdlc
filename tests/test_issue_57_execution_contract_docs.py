from pathlib import Path
import json
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUE_DOC = REPO_ROOT / "docs" / "Issue_57_Python_Execution_Contract.md"
README = REPO_ROOT / "README.md"
SKILL = REPO_ROOT / "SKILL.md"
PROMPTS = REPO_ROOT / "config" / "prompts.json"
PRE_COMMIT_HOOK = REPO_ROOT / ".sdlc_hooks" / "pre-commit"
INSTALL_HOOK = REPO_ROOT / "scripts" / "install_hook.sh"
RUNTIME_PYTHON = "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python"
INSTALLED_COMMIT_STATE = "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/commit_state.py"

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


def _active_prompts():
    return json.loads(_read(PROMPTS))


def test_pre_commit_hook_jit_guidance_uses_controlled_commit_state_command():
    hook = _read(PRE_COMMIT_HOOK)

    assert RUNTIME_PYTHON in hook
    assert INSTALLED_COMMIT_STATE in hook
    assert f"{RUNTIME_PYTHON} {INSTALLED_COMMIT_STATE} --files <path_to_files>" in hook
    assert "commit_state.py --files <path_to_files>" in hook
    assert "python3 ${SDLC_SKILLS_ROOT" not in hook
    assert "python3 ~/.openclaw/skills/leio-sdlc/scripts/commit_state.py" not in hook
    assert "python3 $HOME/.openclaw/skills/leio-sdlc/scripts/commit_state.py" not in hook


def test_install_hook_surface_remains_managed_and_not_manual_activation_based():
    installer = _read(INSTALL_HOOK)

    assert '.sdlc_hooks/pre-commit' in installer or '.sdlc_hooks"/pre-commit' in installer
    assert "SDLC_MANAGED_HOOK=leio-sdlc" in installer
    assert "SDLC_HOOK_SCHEMA_VERSION" in installer
    assert "cp \"$HOOK_SOURCE\" \"$TARGET_DIR/hooks/pre-commit\"" in installer
    assert "chmod +x \"$TARGET_DIR/hooks/pre-commit\"" in installer
    assert "source .venv/bin/activate" not in installer
    assert "python3" not in installer
    assert "pip install" not in installer


def test_active_handoff_prompts_use_deployed_runtime_interpreter_for_orchestrator_commands():
    prompts = _active_prompts()
    runtime_python = "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python"
    installed_orchestrator = "{SDLC_SKILLS_ROOT}/leio-sdlc/scripts/orchestrator.py"
    active_handoff_keys = [
        "handoff_git_checkout_error",
        "handoff_fatal_crash",
        "handoff_startup_validation_failed",
    ]

    for key in active_handoff_keys:
        prompt = prompts[key]
        assert runtime_python in prompt
        assert installed_orchestrator in prompt
        assert f"python3 {installed_orchestrator}" not in prompt
        assert f"python3 `{installed_orchestrator}" not in prompt
        assert "python3 ${SDLC_SKILLS_ROOT}/leio-sdlc/scripts/orchestrator.py" not in prompt
        assert "python3 {SDLC_SKILLS_ROOT}/leio-sdlc/scripts/orchestrator.py" not in prompt


def test_active_handoff_prompt_updates_preserve_manager_failure_semantics():
    prompts = _active_prompts()
    git_checkout = prompts["handoff_git_checkout_error"]
    fatal_crash = prompts["handoff_fatal_crash"]
    startup_validation = prompts["handoff_startup_validation_failed"]
    updated_prompts = "\n".join([git_checkout, fatal_crash, startup_validation])

    assert "[FATAL_GIT]" in git_checkout
    assert "Git checkout failed. Workspace preserved." in git_checkout
    assert "--cleanup" in git_checkout
    assert "quarantine the branch" in git_checkout

    assert "[FATAL_CRASH]" in fatal_crash
    assert "Orchestrator crashed. Process groups reaped. Workspace preserved." in fatal_crash
    assert "read the traceback in logs" in fatal_crash
    assert "--cleanup" in fatal_crash
    assert "quarantine the branch" in fatal_crash

    assert "[FATAL_STARTUP]" in startup_validation
    assert "Startup validation failed (likely executing from the wrong directory)." in startup_validation
    assert "absolute installed path" in startup_validation
    assert "--enable-exec-from-workspace" in startup_validation
    assert "if testing locally" in startup_validation

    assert "|| true" not in updated_prompts
    assert "continue-on-error" not in updated_prompts
    assert "--no-verify" not in updated_prompts
    assert "ignore cleanup" not in updated_prompts.lower()
    assert "ignore startup" not in updated_prompts.lower()
    assert "ignore failed cleanup" not in updated_prompts.lower()


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
