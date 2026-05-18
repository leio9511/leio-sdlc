from pathlib import Path
import json
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
SKILL = REPO_ROOT / "SKILL.md"
ISSUE_DOC = REPO_ROOT / "docs" / "Issue_57_Python_Execution_Contract.md"
PROMPTS = REPO_ROOT / "config" / "prompts.json"
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ACTIVE_FATAL_RECOVERY_PROMPT_KEYS = (
    "handoff_git_checkout_error",
    "handoff_fatal_crash",
    "handoff_startup_validation_failed",
)
FATAL_RECOVERY_CONDITIONS = (
    "git_checkout_error",
    "fatal_crash",
    "startup_validation_failed",
)
REQUIRED_FATAL_RECOVERY_MARKERS = (
    "[FATAL_GIT]",
    "[FATAL_CRASH]",
    "[FATAL_STARTUP]",
    "[ACTION REQUIRED FOR MANAGER]",
)

ACTIVE_DOCS = (README, SKILL, ISSUE_DOC)
RUNTIME_LAUNCH_DOCS = (README, SKILL)
ACTIVE_PLAYBOOKS = (
    REPO_ROOT / "playbooks" / "coder_playbook.md",
    REPO_ROOT / "playbooks" / "planner_playbook.md",
    REPO_ROOT / "playbooks" / "reviewer_playbook.md",
    REPO_ROOT / "playbooks" / "verifier_playbook.md",
)
CODER_PLAYBOOKS = (
    REPO_ROOT / "playbooks" / "coder_playbook.md",
    REPO_ROOT / "playbooks" / "coder_playbook_v2.md",
)

REQUIRED_DEPENDENCY_ENTRY = (
    "requirements.txt at the repository root, currently serving runtime, "
    "development, and test dependencies together"
)
REQUIRED_DEV_CONTEXT = "repository-root .venv"
REQUIRED_RUNTIME_CONTEXT = (
    "deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap"
)
REQUIRED_CORE_GOAL = (
    "Define a controlled, repeatable Python execution contract for local development, testing, "
    "deployed skill runtime, and GitHub CI without depending on unmanaged system Python state."
)
REQUIRED_SMOKE_POLICY = (
    "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, "
    "and startup-path initialization. Do not use full auditor/orchestrator/long-running business "
    "execution as default smoke validation."
)
CONTROLLED_RUNTIME_PYTHON = "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python"
CONTROLLED_DEV_WRAPPER = "./scripts/dev_python.sh"
CONTROLLED_DEV_WRAPPER_ALT = "scripts/dev_python.sh"
CONTROLLED_RUNTIME_GIT_IDENTITY = "scripts/runtime_git_identity.py"
CONTROLLED_RUNTIME_GIT_IDENTITY_COMMAND = (
    f'{CONTROLLED_DEV_WRAPPER} {CONTROLLED_RUNTIME_GIT_IDENTITY} --role coder -- commit -m "feat/fix: <description>"'
)
CONTROLLED_COMMIT_STATE = (
    "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/commit_state.py"
)
CONTROLLED_COMMIT_STATE_GUIDANCE = (
    f"{CONTROLLED_RUNTIME_PYTHON} {CONTROLLED_COMMIT_STATE} --files <path_to_files>"
)
CONTROLLED_ORCHESTRATOR = (
    "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/orchestrator.py"
)
LEGACY_ORCHESTRATOR_PLACEHOLDER = "{SDLC_SKILLS_ROOT}/leio-sdlc/scripts/orchestrator.py"
BARE_ORCHESTRATOR_LAUNCH = "python3 scripts/orchestrator.py"
BARE_RUNTIME_GIT_IDENTITY_LAUNCH = re.compile(r"python3\s+scripts/runtime_git_identity\.py")
BARE_FORMAL_PYTEST = re.compile(r"(?<![-\w./])pytest(?:\s|$)")
BARE_INSTALLED_ORCHESTRATOR_LAUNCH = re.compile(
    r"python3\s+(?:`)?(?:\$\{SDLC_SKILLS_ROOT\}|\{SDLC_SKILLS_ROOT\}|\$HOME/\.openclaw/skills|~/\.openclaw/skills)"
    r"/leio-sdlc/scripts/orchestrator\.py"
)
MANUAL_ACTIVATION = "source .venv/bin/activate"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _active_prompts() -> dict[str, str]:
    return json.loads(_read(PROMPTS))


def _without_fenced_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:bash|shell)?\n(.*?)```", text, flags=re.DOTALL)


def _normalize_echoed_guidance(text: str) -> set[str]:
    commands = set()
    guidance_emitters = ("echo ", "printf '%s\\n' ")
    for line in text.splitlines():
        stripped = line.strip()
        if "commit_state.py" not in stripped:
            continue
        for emitter in guidance_emitters:
            if not stripped.startswith(emitter):
                continue
            guidance = stripped.removeprefix(emitter).strip()
            if len(guidance) >= 2 and guidance[0] == guidance[-1] and guidance[0] in {'"', "'"}:
                guidance = guidance[1:-1]
            commands.add(guidance)
            break
    return commands


def _has_controlled_orchestrator_launch_example(text: str) -> bool:
    for block in _fenced_blocks(text):
        normalized = " ".join(line.strip().rstrip("\\") for line in block.splitlines())
        if CONTROLLED_RUNTIME_PYTHON in normalized and CONTROLLED_ORCHESTRATOR in normalized:
            return True
    return False


def test_active_playbooks_use_controlled_dev_or_runtime_entrypoints():
    for path in ACTIVE_PLAYBOOKS:
        text = _read(path)

        assert BARE_FORMAL_PYTEST.search(text) is None, path
        assert BARE_RUNTIME_GIT_IDENTITY_LAUNCH.search(text) is None, path
        assert BARE_ORCHESTRATOR_LAUNCH not in text, path

    combined = "\n".join(_read(path) for path in ACTIVE_PLAYBOOKS)
    assert "./preflight.sh" in combined
    assert CONTROLLED_DEV_WRAPPER_ALT in combined or CONTROLLED_RUNTIME_PYTHON in combined


def test_coder_playbook_runtime_git_identity_uses_controlled_dev_entrypoint():
    for path in CODER_PLAYBOOKS:
        text = _read(path)

        assert CONTROLLED_RUNTIME_GIT_IDENTITY in text, path
        assert CONTROLLED_RUNTIME_GIT_IDENTITY_COMMAND in text, path
        assert BARE_RUNTIME_GIT_IDENTITY_LAUNCH.search(text) is None, path


def test_playbook_updates_preserve_role_methodology_sections():
    planner = _read(REPO_ROOT / "playbooks" / "planner_playbook.md")
    reviewer = _read(REPO_ROOT / "playbooks" / "reviewer_playbook.md")
    verifier = _read(REPO_ROOT / "playbooks" / "verifier_playbook.md")

    assert "Functional Sequence Slicing" in planner
    assert "Convergence-Oriented Slicing Standard" in planner
    assert "KEY FOCUS AREAS" in reviewer
    assert "Plan Alignment Violation" in reviewer
    assert "Read-Only" in verifier
    assert "Strict Adherence" in verifier



def test_active_docs_state_single_dependency_and_dual_venv_contract():
    for path in ACTIVE_DOCS:
        text = _read(path)

        assert REQUIRED_CORE_GOAL in text, path
        assert REQUIRED_DEPENDENCY_ENTRY in text, path
        assert REQUIRED_DEV_CONTEXT in text, path
        assert REQUIRED_RUNTIME_CONTEXT in text, path
        assert "staging before atomic swap" in text, path


def test_active_runtime_launch_docs_use_controlled_runtime_interpreter():
    for path in RUNTIME_LAUNCH_DOCS:
        text = _read(path)

        assert _has_controlled_orchestrator_launch_example(text), path
        assert BARE_ORCHESTRATOR_LAUNCH not in text, path


def test_active_dev_docs_use_dev_wrapper_not_manual_activation_as_contract():
    for path in ACTIVE_DOCS:
        text = _read(path)
        active_text = _without_fenced_blocks(text)

        assert "scripts/dev_python.sh" in text or "preflight.sh" in text, path
        assert REQUIRED_DEV_CONTEXT in text, path
        assert MANUAL_ACTIVATION not in active_text, path


def test_official_runtime_smoke_policy_is_documented():
    for path in ACTIVE_DOCS:
        text = _read(path)

        assert "scripts/runtime_smoke.py" in text, path
        assert "no-side-effect" in text, path
        assert REQUIRED_SMOKE_POLICY in text, path


def test_active_hooks_use_runtime_interpreter_for_commit_state_guidance():
    for path in (REPO_ROOT / ".sdlc_hooks" / "pre-commit", REPO_ROOT / "scripts" / "pre-commit-payload.sh"):
        guidance = _normalize_echoed_guidance(_read(path))

        assert CONTROLLED_COMMIT_STATE_GUIDANCE in guidance, path


def test_active_hooks_do_not_use_bare_python3_for_commit_state_guidance():
    bare_commit_state_launch = re.compile(r"python3\s+[^\n;]*commit_state\.py")

    for path in (REPO_ROOT / ".sdlc_hooks" / "pre-commit", REPO_ROOT / "scripts" / "pre-commit-payload.sh"):
        text = _read(path)

        assert "python3 ${SDLC_SKILLS_ROOT" not in text, path
        assert "python3 ~/.openclaw/skills" not in text, path
        assert bare_commit_state_launch.search(text) is None, path


def test_active_hook_guidance_payload_matches_installed_hook_source():
    installed_hook_guidance = _normalize_echoed_guidance(_read(REPO_ROOT / ".sdlc_hooks" / "pre-commit"))
    payload_guidance = _normalize_echoed_guidance(_read(REPO_ROOT / "scripts" / "pre-commit-payload.sh"))

    assert CONTROLLED_COMMIT_STATE_GUIDANCE in installed_hook_guidance
    assert CONTROLLED_COMMIT_STATE_GUIDANCE in payload_guidance
    assert installed_hook_guidance == payload_guidance


def test_active_prompts_do_not_reintroduce_contract_critical_bare_python3():
    prompts = _active_prompts()

    for key in ACTIVE_FATAL_RECOVERY_PROMPT_KEYS:
        prompt = prompts[key]

        assert CONTROLLED_RUNTIME_PYTHON in prompt, key
        assert LEGACY_ORCHESTRATOR_PLACEHOLDER in prompt, key
        assert f"{CONTROLLED_RUNTIME_PYTHON} {LEGACY_ORCHESTRATOR_PLACEHOLDER}" in prompt, key
        assert BARE_INSTALLED_ORCHESTRATOR_LAUNCH.search(prompt) is None, key

    happy_path = prompts["handoff_happy_path"]
    assert "issue_tracker/scripts/issues.py" in happy_path
    assert "outside the leio-sdlc runtime contract" in happy_path
    assert f"{CONTROLLED_RUNTIME_PYTHON} {{SDLC_SKILLS_ROOT}}/issue_tracker/scripts/issues.py" not in happy_path


def test_active_prompts_use_runtime_interpreter_for_orchestrator_recovery_examples():
    test_active_prompts_do_not_reintroduce_contract_critical_bare_python3()


def test_active_prompts_preserve_required_fatal_recovery_tokens():
    prompts = _active_prompts()
    combined_prompts = "\n".join(prompts[key] for key in ACTIVE_FATAL_RECOVERY_PROMPT_KEYS)

    for marker in REQUIRED_FATAL_RECOVERY_MARKERS:
        assert marker in combined_prompts

    assert "--cleanup" in prompts["handoff_git_checkout_error"]
    assert "quarantine the branch" in prompts["handoff_git_checkout_error"]
    assert "--cleanup" in prompts["handoff_fatal_crash"]
    assert "quarantine the branch" in prompts["handoff_fatal_crash"]
    assert "absolute installed path" in prompts["handoff_startup_validation_failed"]
    assert "--enable-exec-from-workspace" in prompts["handoff_startup_validation_failed"]


def test_active_prompts_preserve_recovery_placeholders_after_handoff_interpolation(monkeypatch):
    import config
    from handoff_prompter import HandoffPrompter

    runtime_root = "/tmp/example-runtime-root"
    monkeypatch.setattr(config, "SDLC_RUNTIME_DIR", runtime_root, raising=False)

    for condition in FATAL_RECOVERY_CONDITIONS:
        prompt = HandoffPrompter.get_prompt(condition)

        assert "{SDLC_SKILLS_ROOT}" not in prompt, condition
        assert f"{runtime_root}/leio-sdlc/scripts/orchestrator.py" in prompt, condition
        assert CONTROLLED_RUNTIME_PYTHON in prompt, condition


def test_active_prompts_preserve_recovery_placeholders_after_handoff_interpolation_legacy_fallback(
    monkeypatch,
):
    import config
    from handoff_prompter import HandoffPrompter

    monkeypatch.delattr(config, "SDLC_RUNTIME_DIR", raising=False)

    for condition in FATAL_RECOVERY_CONDITIONS:
        prompt = HandoffPrompter.get_prompt(condition)

        assert "{SDLC_SKILLS_ROOT}" not in prompt, condition
        assert f"{config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/orchestrator.py" in prompt, condition
        assert CONTROLLED_RUNTIME_PYTHON in prompt, condition


def test_prompt_and_hook_updates_do_not_claim_cross_skill_runtime_control():
    prompts = _active_prompts()
    happy_path = prompts["handoff_happy_path"]

    assert "issue_tracker/scripts/issues.py" in happy_path
    assert "outside the leio-sdlc runtime contract" in happy_path
    assert "issue_tracker skill command" in happy_path
    assert "controlled runtime" not in happy_path.lower()
    assert "leio-sdlc/.venv/bin/python {SDLC_SKILLS_ROOT}/issue_tracker" not in happy_path

    for path in (REPO_ROOT / ".sdlc_hooks" / "pre-commit", REPO_ROOT / "scripts" / "pre-commit-payload.sh"):
        text = _read(path).lower()

        assert "pm-skill" not in text, path
        assert "other skill" not in text, path
        assert "all skill" not in text, path
        assert "cross-skill" not in text, path


def test_active_prompts_preserve_required_handoff_tokens_and_placeholders():
    prompts = _active_prompts()
    json.dumps(prompts)

    required_by_key = {
        "handoff_happy_path": ("[SUCCESS_HANDOFF]", "[ACTION REQUIRED FOR MANAGER]", "{SDLC_SKILLS_ROOT}"),
        "handoff_git_checkout_error": ("[FATAL_GIT]", "[ACTION REQUIRED FOR MANAGER]", "{SDLC_SKILLS_ROOT}"),
        "handoff_fatal_crash": ("[FATAL_CRASH]", "[ACTION REQUIRED FOR MANAGER]", "{SDLC_SKILLS_ROOT}"),
        "handoff_startup_validation_failed": ("[FATAL_STARTUP]", "[ACTION REQUIRED FOR MANAGER]", "{SDLC_SKILLS_ROOT}"),
    }

    for key, required_tokens in required_by_key.items():
        prompt = prompts[key]
        for token in required_tokens:
            assert token in prompt, (key, token)

    assert "<ISSUE-ID>" in prompts["handoff_happy_path"]
    assert "--cleanup" in prompts["handoff_git_checkout_error"]
    assert "--cleanup" in prompts["handoff_fatal_crash"]
    assert "--enable-exec-from-workspace" in prompts["handoff_startup_validation_failed"]
