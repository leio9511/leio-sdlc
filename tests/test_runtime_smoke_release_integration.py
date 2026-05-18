import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "skill_test_runner.sh"
BUILD_RELEASE = REPO_ROOT / "scripts" / "build_release.sh"
SMOKE_POLICY = "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation."


def _copy_release_inputs(source_root, target_root):
    for path in source_root.iterdir():
        if path.name in {".git", ".venv", ".dist", ".pytest_cache", "__pycache__"}:
            continue
        destination = target_root / path.name
        if path.is_dir():
            shutil.copytree(
                path,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
        elif path.is_file():
            shutil.copy2(path, destination)


def _write_fake_openclaw(bin_dir):
    fake_openclaw = bin_dir / "openclaw"
    fake_openclaw.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$FAKE_OPENCLAW_ARGS_LOG\"\n"
        "token=$(printf '%s\\n' \"$@\" | sed -n \"s/.*validation token '\\([^']*\\)'.*/\\1/p\" | head -n 1)\n"
        "printf '%s\\n' \"openclaw agent protocol invoked\"\n"
        "printf '%s\\n' \"PASSED_${token:-compat}\"\n",
        encoding="utf-8",
    )
    fake_openclaw.chmod(fake_openclaw.stat().st_mode | stat.S_IXUSR)
    return fake_openclaw


def test_build_release_packages_runtime_smoke_and_guard_support_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _copy_release_inputs(REPO_ROOT, workspace)

    result = subprocess.run(
        ["bash", "scripts/build_release.sh"],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    dist = workspace / ".dist"
    runtime_smoke = dist / "scripts" / "runtime_smoke.py"
    runtime_guard = dist / "scripts" / "runtime_launch_guard.py"
    assert runtime_smoke.exists()
    assert runtime_guard.exists()
    assert (dist / "scripts" / "config.py").exists()
    assert (dist / "scripts" / "utils_json.py").exists()
    assert not (dist / "tests").exists()

    help_result = subprocess.run(
        [sys.executable, str(runtime_smoke), "--help"],
        cwd=dist,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert "Official minimal no-side-effect leio-sdlc runtime smoke path" in help_result.stdout
    assert SMOKE_POLICY in help_result.stdout


def test_skill_test_runner_runtime_smoke_mode_uses_skill_venv_python_not_ambient_python3(tmp_path):
    skill_root = tmp_path / "skill"
    scripts_dir = skill_root / "scripts"
    runtime_python = skill_root / ".venv" / "bin" / "python"
    scripts_dir.mkdir(parents=True)
    runtime_python.parent.mkdir(parents=True)
    invocation_log = tmp_path / "runtime-python-invocation.log"

    runtime_python.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$0\" > {invocation_log}\n"
        f"printf '%s\\n' \"$@\" >> {invocation_log}\n"
        "exit 0\n",
        encoding="utf-8",
    )
    runtime_python.chmod(runtime_python.stat().st_mode | stat.S_IXUSR)
    (scripts_dir / "runtime_smoke.py").write_text("# smoke placeholder\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(RUNNER), "--runtime-smoke", str(skill_root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    invocation = invocation_log.read_text(encoding="utf-8")
    assert invocation.splitlines()[0] == str(runtime_python)
    assert str(scripts_dir / "runtime_smoke.py") in invocation
    assert "--skill-root" in invocation
    assert str(skill_root) in invocation
    assert "--expected-runtime-python" in invocation
    assert str(runtime_python) in invocation
    assert "python3" not in invocation
    assert "ambient python3" not in result.stdout


def test_skill_markdown_uses_controlled_runtime_interpreter_for_active_launch_examples():
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    active_skill = re.sub(r"```.*?```", "", skill, flags=re.DOTALL)

    controlled_python = "${SDLC_SKILLS_ROOT:-$HOME/.openclaw/skills}/leio-sdlc/.venv/bin/python"
    assert controlled_python in skill
    assert "scripts/orchestrator.py" in skill
    assert "scripts/runtime_smoke.py" in skill
    assert SMOKE_POLICY in skill
    assert "background: true" in skill
    assert "timeout: 0" in skill
    assert "python3" not in active_skill

    for block in re.findall(r"```bash\n(.*?)```", skill, flags=re.DOTALL):
        if "scripts/orchestrator.py" in block:
            assert controlled_python in block
            assert "python3" not in block


def test_skill_test_runner_existing_agent_protocol_remains_backward_compatible(tmp_path):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_openclaw(bin_dir)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_OPENCLAW_ARGS_LOG"] = str(tmp_path / "openclaw-args.log")
    env["FAKE_OPENCLAW_TOKEN"] = "compat"

    result = subprocess.run(
        ["bash", str(RUNNER), str(skill_root), "READY?"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Spawning sub-agent test runner" in result.stdout
    assert "Test Prompt: READY?" in result.stdout
    assert "Validation Token:" in result.stdout
    assert "Evaluation Phase" in result.stdout
    args_log = Path(env["FAKE_OPENCLAW_ARGS_LOG"]).read_text(encoding="utf-8")
    assert "agent" in args_log
    assert "--session-id" in args_log
    assert "PASSED_" in args_log or "PASSED_compat" not in result.stderr


def test_runner_runtime_smoke_mode_fails_clearly_when_runtime_venv_missing(tmp_path):
    skill_root = tmp_path / "skill"
    (skill_root / "scripts").mkdir(parents=True)
    (skill_root / "scripts" / "runtime_smoke.py").write_text("# smoke placeholder\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(RUNNER), "--runtime-smoke", str(skill_root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode != 0
    assert "Missing explicit runtime interpreter" in result.stderr
    assert str(skill_root / ".venv" / "bin" / "python") in result.stderr
    assert "will not use ambient python3" in result.stderr
    assert "create the runtime .venv" in result.stderr
