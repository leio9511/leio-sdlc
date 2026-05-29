import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path to allow import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import spawn_auditor
from test_path_helpers import exists_except_engine_local, static_root


VALID_PRD_CONTENT = (
    "1. Context & Problem\n"
    "2. Requirements & User Stories\n"
    "3. Architecture & Technical Strategy\n"
    "4. Acceptance Criteria\n"
    "5. Overall Test Strategy\n"
    "6. Framework Modifications\n"
    "7. Hardcoded Content"
)


def _write_valid_prd(path: Path) -> None:
    path.write_text(VALID_PRD_CONTENT)


def test_spawn_auditor_missing_channel(capsys):
    # Missing required argument will cause argparse to exit with code 2
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md", "--workdir", "."]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()

        assert e.value.code == 2


@patch("subprocess.run")
@patch("shutil.which", return_value="/mock/openclaw")
def test_spawn_auditor_invalid_channel_handshake_fail(mock_which, mock_run, capsys, monkeypatch):
    # Simulate a failed handshake from the openclaw cli
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "Invalid channel format"

    monkeypatch.setenv("SDLC_TEST_MODE", "false")
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md", "--workdir", ".", "--channel", "invalid_format"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()

        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "[FATAL] Notification delivery failed" in captured.err


def test_spawn_auditor_guardrail(capsys):
    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", "dummy.md", "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()

        assert e.value.code == 1
        captured = capsys.readouterr()
        assert "Startup validation failed" in captured.out


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
def test_spawn_auditor_valid_channel_success(mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "valid_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_TEST_MODE", "true")
    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("MOCK_AUDIT_RESULT", "APPROVE")

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out

    mock_notify.assert_any_call("test_channel", "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": str(prd_file)})


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
def test_auditor_rejected_returns_exit_0(mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "rejected_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_TEST_MODE", "true")
    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("MOCK_AUDIT_RESULT", "REJECT")

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out

    mock_notify.assert_any_call("test_channel", "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": str(prd_file)})


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
def test_auditor_notifies_on_missing_sections(mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "malformed_prd.md"
    prd_file.write_text("This is a malformed PRD without any sections.")

    monkeypatch.setenv("SDLC_TEST_MODE", "true")

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()

        # Should exit with code 0 per spawn_auditor logic
        assert e.value.code == 0

    captured = capsys.readouterr()
    expected_msg = "REJECTED: PRD structure does not match the mandatory template. Missing sections: 1. Context & Problem, 2. Requirements & User Stories, 3. Architecture & Technical Strategy, 4. Acceptance Criteria, 5. Overall Test Strategy, 6. Framework Modifications. DO NOT overwrite the template generated by init_prd.py with raw write tools."

    assert expected_msg in captured.out
    mock_notify.assert_any_call("test_channel", expected_msg, "auditor_rejected", {"prd_file": str(prd_file)})


def test_spawn_auditor_env_overrides_restore_baseline(monkeypatch):
    assert os.environ["SDLC_TEST_MODE"] == "true"
    monkeypatch.setenv("SDLC_TEST_MODE", "false")
    assert os.environ["SDLC_TEST_MODE"] == "false"


def test_spawn_auditor_env_baseline_restored_for_next_test():
    assert os.environ["SDLC_TEST_MODE"] == "true"


def test_prd_template_contains_section_7():
    template_path = os.path.join(os.path.dirname(__file__), "..", "skills", "pm-skill", "TEMPLATES", "PRD.md.template")
    if not os.path.exists(template_path):
        template_path = os.path.join(os.path.dirname(__file__), "..", ".dist", "skills", "pm-skill", "TEMPLATES", "PRD.md.template")

    with open(template_path, "r") as f:
        content = f.read()

    assert "7. Hardcoded Content (硬编码内容)" in content
    assert "Anti-Hallucination Policy (防幻觉策略)" in content
    # Assert it is at the very end
    # Because of possible newlines, we strip the content and check if it ends with the block
    assert content.strip().endswith("```")


@patch("utils_api_key.assign_gemini_api_key")
@patch("spawn_auditor.invoke_agent")
def test_auditor_uses_shared_key_utility(mock_invoke_agent, mock_assign_api_key, tmp_path, monkeypatch):
    mock_invoke_agent.return_value = MagicMock(stdout='{"status": "APPROVED"}', returncode=0)
    mock_assign_api_key.return_value = "TEST_API_KEY"

    prd_file = tmp_path / "dummy_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))

    args = ["--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "slack:C123"]
    with patch("sys.argv", ["spawn_auditor.py"] + args):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0

    mock_assign_api_key.assert_called_once()
    assert os.environ.get("GEMINI_API_KEY") == "TEST_API_KEY"


def test_spawn_auditor_fails_fast_on_handshake_failure():
    # If handshake fails, sys.exit(1) should be called before audit execution
    with patch("agent_driver.send_ignition_handshake", side_effect=SystemExit(1)) as mock_handshake:
        with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", "test.md", "--workdir", ".", "--channel", "invalid:channel", "--enable-exec-from-workspace"]):
            with pytest.raises(SystemExit) as exc:
                spawn_auditor.main()
            assert exc.value.code == 1
            mock_handshake.assert_called_once_with("invalid:channel")


@patch("spawn_auditor.config")
@patch("runtime_launch_guard.config")
@patch("sys.argv", ["/custom_runtime_dir/spawn_auditor.py", "--prd-file", "dummy", "--workdir", "dummy", "--channel", "dummy"])
def test_spawn_auditor_startup_validation_uses_allowed_runtime_roots(mock_runtime_guard_config, mock_config, tmp_path):
    for cfg in (mock_config, mock_runtime_guard_config):
        cfg.ALLOWED_RUNTIME_ROOTS_CONFIG_KEY = "ALLOWED_RUNTIME_ROOTS"
        cfg.DEFAULT_ALLOWED_RUNTIME_ROOTS = ["/custom_runtime_dir"]
        cfg.DEFAULT_LLM_ENGINE = "gemini"
        cfg.DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
        cfg.load_or_merge_config.return_value = {
            "ALLOWED_RUNTIME_ROOTS": ["/custom_runtime_dir"],
        }
        cfg.get_allowed_runtime_roots.return_value = ["/custom_runtime_dir"]

    prd_file = tmp_path / "dummy_prd.md"
    _write_valid_prd(prd_file)

    with patch.object(sys, "argv", ["spawn_auditor.py", "--prd-file", str(prd_file.resolve()), "--workdir", str(tmp_path), "--channel", "dummy", "--enable-exec-from-workspace"]):
        try:
            prd_file_abs = str(prd_file.resolve())

            def _spawn_auditor_exists(path):
                return path == prd_file_abs

            with patch("spawn_auditor.invoke_agent", side_effect=SystemExit(0)), \
                 patch("spawn_auditor.os.makedirs"), \
                 patch("spawn_auditor.os.chdir"), \
                 patch("spawn_auditor.envelope_assembler.save_envelope_artifacts"), \
                 patch("engine_registry.os.path.exists", return_value=False), \
                 patch("spawn_auditor.os.path.exists", side_effect=_spawn_auditor_exists), \
                 patch("agent_driver.send_ignition_handshake"), \
                 patch("agent_driver.notify_channel"), \
                 patch("utils_api_key.setup_spawner_api_key"):
                spawn_auditor.main()
        except SystemExit as e:
            if e.code == 1:
                pytest.fail("spawn_auditor exited fatally, meaning startup validation failed unexpectedly")


@patch("spawn_auditor.config")
@patch("runtime_launch_guard.config")
@patch("sys.argv", ["/invalid_dir/spawn_auditor.py", "--prd-file", "dummy", "--workdir", "dummy", "--channel", "dummy"])
def test_spawn_auditor_startup_validation_rejects_path_outside_allowed_runtime_roots(mock_runtime_guard_config, mock_config):
    for cfg in (mock_config, mock_runtime_guard_config):
        cfg.ALLOWED_RUNTIME_ROOTS_CONFIG_KEY = "ALLOWED_RUNTIME_ROOTS"
        cfg.DEFAULT_ALLOWED_RUNTIME_ROOTS = ["/custom_runtime_dir"]
        cfg.DEFAULT_LLM_ENGINE = "gemini"
        cfg.DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
        cfg.load_or_merge_config.return_value = {
            "ALLOWED_RUNTIME_ROOTS": ["/custom_runtime_dir"],
        }
        cfg.get_allowed_runtime_roots.return_value = ["/custom_runtime_dir"]
    with patch("handoff_prompter.HandoffPrompter.get_prompt", return_value="failed"), \
         patch("utils_api_key.setup_spawner_api_key"):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 1


# --- Auditor Result-Source Hotfix Tests ---

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_file_first_success(mock_invoke_agent, mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "file_first_success_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "false")

    canonical_file = tmp_path / "auditor_verdict.json"
    canonical_file.write_text(json.dumps({"status": "APPROVED", "comments": "File approved"}))

    mock_result = MagicMock()
    mock_result.stdout = "Here is some conversational text without JSON."
    mock_invoke_agent.return_value = mock_result

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out
    mock_notify.assert_any_call("test_channel", "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": str(prd_file)})


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_file_first_rejection(mock_invoke_agent, mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "file_first_rejection_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "false")

    canonical_file = tmp_path / "auditor_verdict.json"
    canonical_file.write_text(json.dumps({"status": "REJECTED", "comments": "File rejected"}))

    mock_result = MagicMock()
    mock_result.stdout = "Conversational text without JSON."
    mock_invoke_agent.return_value = mock_result

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_legacy_stdout_fallback(mock_invoke_agent, mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "legacy_stdout_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "false")

    mock_result = MagicMock()
    mock_result.stdout = '```json\n{"status": "APPROVED", "comments": "Stdout fallback"}\n```'
    mock_invoke_agent.return_value = mock_result

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[WARNING] Canonical verdict file missing or invalid, falling back to stdout parsing" in captured.out
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_conflicting_stdout_and_file(mock_invoke_agent, mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "conflicting_stdout_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "false")

    canonical_file = tmp_path / "auditor_verdict.json"
    canonical_file.write_text(json.dumps({"status": "REJECTED", "comments": "File says reject"}))

    mock_result = MagicMock()
    mock_result.stdout = '{"status": "APPROVED"}'
    mock_invoke_agent.return_value = mock_result

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "Conflict detected: canonical file says REJECTED but stdout says APPROVED. Using file verdict." in captured.out
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_missing_file_invalid_stdout(mock_invoke_agent, mock_handshake, mock_notify, capsys, monkeypatch, tmp_path):
    prd_file = tmp_path / "missing_file_invalid_stdout_prd.md"
    _write_valid_prd(prd_file)

    monkeypatch.setenv("SDLC_RUN_DIR", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "false")

    mock_result = MagicMock()
    mock_result.stdout = "Nothing to see here."
    mock_invoke_agent.return_value = mock_result

    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", str(tmp_path), "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0

    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
