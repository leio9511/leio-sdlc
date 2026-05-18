from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
SKILL = REPO_ROOT / "SKILL.md"
ISSUE_DOC = REPO_ROOT / "docs" / "Issue_57_Python_Execution_Contract.md"

ACTIVE_DOCS = (README, SKILL, ISSUE_DOC)
RUNTIME_LAUNCH_DOCS = (README, SKILL)

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
CONTROLLED_COMMIT_STATE = (
    "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/commit_state.py"
)
CONTROLLED_COMMIT_STATE_GUIDANCE = (
    f"{CONTROLLED_RUNTIME_PYTHON} {CONTROLLED_COMMIT_STATE} --files <path_to_files>"
)
CONTROLLED_ORCHESTRATOR = (
    "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/scripts/orchestrator.py"
)
BARE_ORCHESTRATOR_LAUNCH = "python3 scripts/orchestrator.py"
MANUAL_ACTIVATION = "source .venv/bin/activate"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def test_prompt_and_hook_updates_do_not_claim_cross_skill_runtime_control():
    for path in (REPO_ROOT / ".sdlc_hooks" / "pre-commit", REPO_ROOT / "scripts" / "pre-commit-payload.sh"):
        text = _read(path).lower()

        assert "pm-skill" not in text, path
        assert "other skill" not in text, path
        assert "all skill" not in text, path
        assert "cross-skill" not in text, path
