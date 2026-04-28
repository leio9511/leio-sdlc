import os
import sys
import json
import pytest
from unittest.mock import MagicMock, mock_open, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
import agent_driver
import config


class CommandRun:
    def __init__(self):
        self.commands = []

    def __call__(self, cmd, *args, **kwargs):
        self.commands.append(cmd)
        if cmd[:2] == ["mock_openclaw", "agents"] and cmd[2:] == ["list"]:
            return MagicMock(returncode=0, stdout="other-agent\n", stderr="")
        if cmd[:3] == ["mock_openclaw", "agents", "add"]:
            return MagicMock(returncode=0, stdout="created", stderr="")
        if cmd[:2] == ["mock_openclaw", "agent"]:
            return MagicMock(returncode=0, stdout="openclaw ok", stderr="")
        if cmd and cmd[0] == "mock_gemini" and "--list-sessions" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        if cmd and cmd[0] == "mock_gemini":
            return MagicMock(returncode=0, stdout="gemini ok", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")


def _invoke_with_fake_prompt(env, run_side_effect, *, session_key="baseline-session", exists=None):
    exists = exists or (lambda path: False)
    with patch.dict(os.environ, env, clear=True), \
         patch("agent_driver.tempfile.mkstemp", return_value=(3, f"/mock/tmp/sdlc_prompt_{session_key}.txt")), \
         patch("agent_driver.os.fdopen", mock_open()), \
         patch("agent_driver.os.chmod"), \
         patch("agent_driver.os.remove"), \
         patch("agent_driver.os.path.exists", side_effect=exists), \
         patch("agent_driver.subprocess.run", side_effect=run_side_effect) as mock_run:
        result = agent_driver.invoke_agent("characterize current behavior", session_key=session_key)
    return result, mock_run


def test_legacy_gemini_fresh_command_is_characterized():
    resolver_calls = []

    def fake_resolve(name):
        resolver_calls.append(name)
        return f"mock_{name}"

    with patch("agent_driver.resolve_cmd", side_effect=fake_resolve):
        result, mock_run = _invoke_with_fake_prompt(
            {"LLM_DRIVER": "gemini", "SDLC_MODEL": "gemini-baseline-model"},
            [
                MagicMock(returncode=0, stdout="gemini ok", stderr=""),
                MagicMock(returncode=0, stdout="[]", stderr=""),
            ],
            session_key="gemini-fresh",
        )

    assert result.stdout == "gemini ok"
    assert resolver_calls == ["gemini"]
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd == [
        "mock_gemini",
        "--yolo",
        "-p",
        "Read your complete task instructions from /mock/tmp/sdlc_prompt_gemini-fresh.txt. Do not modify this file.",
        "--model",
        "gemini-baseline-model",
    ]


def test_legacy_gemini_resume_command_is_characterized():
    def fake_exists(path):
        return path.endswith(".session_map_gemini-resume.json")

    with patch("agent_driver.resolve_cmd", return_value="mock_gemini"), \
         patch("builtins.open", mock_open(read_data='{"actual_id": "ACTUAL_GEMINI_SESSION"}')):
        result, mock_run = _invoke_with_fake_prompt(
            {"LLM_DRIVER": "gemini", "SDLC_MODEL": "fresh-model-must-not-render"},
            [MagicMock(returncode=0, stdout="resumed", stderr="")],
            session_key="gemini-resume",
            exists=fake_exists,
        )

    assert result.stdout == "resumed"
    cmd = mock_run.call_args_list[0][0][0]
    assert cmd == [
        "mock_gemini",
        "--yolo",
        "-p",
        "Read your complete task instructions from /mock/tmp/sdlc_prompt_gemini-resume.txt. Do not modify this file.",
        "-r",
        "ACTUAL_GEMINI_SESSION",
    ]
    assert "--model" not in cmd


def test_legacy_gemini_session_capture_is_path_based_until_registry_pr():
    handle = mock_open()
    session_listing = [
        {"id": "IGNORE_PROMPT_TEXT", "prompt": "Read your complete task instructions from another file."},
        {"id": "CAPTURED_BY_TEMP_PATH", "prompt": "bootstrap via /mock/tmp/sdlc_prompt_capture-me.txt"},
    ]

    with patch("agent_driver.resolve_cmd", return_value="mock_gemini"), \
         patch("builtins.open", handle):
        result, mock_run = _invoke_with_fake_prompt(
            {"LLM_DRIVER": "gemini"},
            [
                MagicMock(returncode=0, stdout="fresh success", stderr=""),
                MagicMock(returncode=0, stdout=json.dumps(session_listing), stderr=""),
            ],
            session_key="capture-me",
        )

    assert result.stdout == "fresh success"
    assert mock_run.call_args_list[1][0][0] == ["mock_gemini", "--list-sessions", "-o", "json"]
    written_data = "".join(call.args[0] for call in handle().write.call_args_list)
    assert json.loads(written_data) == {"actual_id": "CAPTURED_BY_TEMP_PATH"}


def test_openclaw_model_specific_agent_creation_is_characterized():
    recorder = CommandRun()

    def fake_resolve(name):
        assert name == "openclaw"
        return "mock_openclaw"

    with patch("agent_driver.resolve_cmd", side_effect=fake_resolve), \
         patch("agent_driver.os.makedirs"), \
         patch("os.listdir", return_value=["AGENTS.md"]), \
         patch("os.path.isdir", return_value=False), \
         patch("shutil.copy2"), \
         patch("shutil.copytree"):
        result, _ = _invoke_with_fake_prompt(
            {"LLM_DRIVER": "openclaw", "SDLC_MODEL": "my/model:1", "HOME_MOCK": "/tmp/mock_home"},
            recorder,
            session_key="openclaw-create",
            exists=lambda path: True if path.endswith("TEMPLATES/openclaw_execution_agent") else False,
        )

    assert result.stdout == "openclaw ok"
    agent_id = "sdlc-generic-openclaw-my-model-1"
    create_cmd = recorder.commands[1]
    assert create_cmd == [
        "mock_openclaw",
        "agents",
        "add",
        agent_id,
        "--non-interactive",
        "--model",
        "my/model:1",
        "--workspace",
        f"/tmp/mock_home/.openclaw/agents/{agent_id}/workspace",
    ]
    run_cmd = recorder.commands[2]
    assert run_cmd == [
        "mock_openclaw",
        "agent",
        "--agent",
        agent_id,
        "--session-id",
        "openclaw-create",
        "-m",
        "Read your complete task instructions from /mock/tmp/sdlc_prompt_openclaw-create.txt. Do not modify this file.",
    ]


def test_openclaw_model_mismatch_guardrail_is_characterized(capsys):
    list_res = MagicMock(
        returncode=0,
        stdout="- sdlc-generic-openclaw-gpt\n  Model: gemini-3.1-pro-preview\n",
        stderr="",
    )

    with patch.dict(os.environ, {"LLM_DRIVER": "openclaw", "SDLC_MODEL": "gpt"}, clear=True), \
         patch("agent_driver.resolve_cmd", return_value="mock_openclaw"), \
         patch("agent_driver.tempfile.mkstemp", return_value=(3, "/mock/tmp/sdlc_prompt_mismatch.txt")), \
         patch("agent_driver.os.fdopen", mock_open()), \
         patch("agent_driver.os.chmod"), \
         patch("agent_driver.os.remove"), \
         patch("agent_driver.os.path.exists", return_value=False), \
         patch("agent_driver.subprocess.run", side_effect=[list_res, list_res]):
        with pytest.raises(SystemExit) as exc:
            agent_driver.invoke_agent("task", session_key="mismatch")

    assert exc.value.code == 1
    assert capsys.readouterr().err.strip() == config.OPENCLAW_MODEL_MISMATCH_ERROR.format(
        requested_model="gpt",
        agent_id="sdlc-generic-openclaw-gpt",
        actual_model="gemini-3.1-pro-preview",
    )


def test_legacy_model_precedence_is_characterized():
    def captured_model(env):
        with patch("agent_driver.resolve_cmd", return_value="mock_gemini"):
            _, mock_run = _invoke_with_fake_prompt(
                env,
                [
                    MagicMock(returncode=0, stdout="ok", stderr=""),
                    MagicMock(returncode=0, stdout="[]", stderr=""),
                ],
                session_key="model-precedence",
            )
        cmd = mock_run.call_args_list[0][0][0]
        return cmd[cmd.index("--model") + 1]

    assert captured_model(
        {"LLM_DRIVER": "gemini", "SDLC_MODEL": "sdlc-wins", "TEST_MODEL": "test-loses"}
    ) == "sdlc-wins"
    assert captured_model({"LLM_DRIVER": "gemini", "TEST_MODEL": "test-fallback"}) == "test-fallback"
    assert captured_model({"LLM_DRIVER": "gemini"}) == config.DEFAULT_GEMINI_MODEL


def test_absent_llm_driver_defaults_to_openclaw_in_invoke_agent():
    recorder = CommandRun()
    with patch("agent_driver.resolve_cmd", return_value="mock_openclaw"), \
         patch("agent_driver.os.makedirs"), \
         patch("os.listdir", return_value=[]), \
         patch("shutil.copy2"), \
         patch("shutil.copytree"):
        result, _ = _invoke_with_fake_prompt(
            {"SDLC_MODEL": "gpt", "HOME_MOCK": "/tmp/mock_home"},
            recorder,
            session_key="default-engine",
            exists=lambda path: path.endswith("TEMPLATES/openclaw_execution_agent"),
        )

    assert result.stdout == "openclaw ok"
    assert recorder.commands[0] == ["mock_openclaw", "agents", "list"]
    assert recorder.commands[2][:4] == [
        "mock_openclaw",
        "agent",
        "--agent",
        "sdlc-generic-openclaw-gpt",
    ]


def test_no_codex_registry_behavior_exists_in_characterization_pr():
    source_path = os.path.join(os.path.dirname(__file__), "../scripts/agent_driver.py")
    with open(source_path, "r", encoding="utf-8") as source:
        agent_driver_source = source.read()

    assert 'resolve_cmd("codex")' not in agent_driver_source
    assert "codex exec" not in agent_driver_source
    assert "handle_acquisition_strategy" not in agent_driver_source
    assert "engine registry" not in agent_driver.invoke_agent.__doc__.lower()
