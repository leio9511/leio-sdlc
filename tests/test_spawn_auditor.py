import pytest
import os
import sys
import tempfile
import json
from unittest.mock import patch, MagicMock
import subprocess

# Add scripts directory to path to allow import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import spawn_auditor

def test_spawn_auditor_missing_channel(capsys):
    # Missing required argument will cause argparse to exit with code 2
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md", "--workdir", "."]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        assert e.value.code == 2

@patch("subprocess.run")
@patch('shutil.which', return_value='/mock/openclaw')
def test_spawn_auditor_invalid_channel_handshake_fail(mock_which, mock_run, capsys):
    # Simulate a failed handshake from the openclaw cli
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = "Invalid channel format"
    
    os.environ["SDLC_TEST_MODE"] = "false"
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
def test_spawn_auditor_valid_channel_success(mock_handshake, mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    os.environ["MOCK_AUDIT_RESULT"] = "APPROVE"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0
        
    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out
    
    mock_notify.assert_any_call("test_channel", "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": prd_file})
    os.remove(prd_file)


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
def test_auditor_rejected_returns_exit_0(mock_handshake, mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    os.environ["MOCK_AUDIT_RESULT"] = "REJECT"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 0
        
    captured = capsys.readouterr()
    assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
    
    mock_notify.assert_any_call("test_channel", "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": prd_file})
    os.remove(prd_file)


@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
def test_auditor_notifies_on_missing_sections(mock_handshake, mock_notify, capsys):
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
        # Malformed PRD: missing all mandatory sections
        f.write(b"This is a malformed PRD without any sections.")
        prd_file = f.name
        
    os.environ["SDLC_TEST_MODE"] = "true"
    
    with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", ".", "--channel", "test_channel"]):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        
        # Should exit with code 0 per spawn_auditor logic
        assert e.value.code == 0
        
    captured = capsys.readouterr()
    expected_msg = "REJECTED: PRD structure does not match the mandatory template. Missing sections: 1. Context & Problem, 2. Requirements & User Stories, 3. Architecture & Technical Strategy, 4. Acceptance Criteria, 5. Overall Test Strategy, 6. Framework Modifications. DO NOT overwrite the template generated by init_prd.py with raw write tools."
    
    assert expected_msg in captured.out
    mock_notify.assert_any_call("test_channel", expected_msg, "auditor_rejected", {"prd_file": prd_file})
    
    os.remove(prd_file)

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
def test_auditor_uses_shared_key_utility(mock_invoke_agent, mock_assign_api_key, tmp_path):
    mock_invoke_agent.return_value = MagicMock(stdout='{"status": "APPROVED"}', returncode=0)
    mock_assign_api_key.return_value = "TEST_API_KEY"
    
    prd_file = tmp_path / "dummy_prd.md"
    prd_file.write_text("1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
    
    workdir = str(tmp_path)
    
    args = ["--enable-exec-from-workspace", "--prd-file", str(prd_file), "--workdir", workdir, "--channel", "slack:C123"]
    
    original_environ = dict(os.environ)
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]
        
    try:
        with patch("sys.argv", ["spawn_auditor.py"] + args):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                with pytest.raises(SystemExit) as e:
                    import spawn_auditor
                    spawn_auditor.main()
                assert e.value.code == 0
            
        mock_assign_api_key.assert_called_once()
        assert os.environ.get("GEMINI_API_KEY") == "TEST_API_KEY"
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import spawn_auditor

def test_spawn_auditor_fails_fast_on_handshake_failure():
    # If handshake fails, sys.exit(1) should be called before audit execution
    with patch("agent_driver.send_ignition_handshake", side_effect=SystemExit(1)) as mock_handshake:
        with patch.object(sys, 'argv', ['spawn_auditor.py', '--prd-file', 'test.md', '--workdir', '.', '--channel', 'invalid:channel', '--enable-exec-from-workspace']):
            with pytest.raises(SystemExit) as exc:
                spawn_auditor.main()
            assert exc.value.code == 1
            mock_handshake.assert_called_once_with('invalid:channel')


from unittest.mock import patch, MagicMock
@patch("spawn_auditor.config")
@patch("sys.argv", ["/custom_runtime_dir/spawn_auditor.py", "--prd-file", "dummy", "--workdir", "dummy", "--channel", "dummy"])
def test_spawn_auditor_startup_validation_uses_runtime_dir(mock_config):
    mock_config.SDLC_RUNTIME_DIR = "/custom_runtime_dir"
    mock_config.DEFAULT_LLM_ENGINE = "gemini"
    import spawn_auditor
    
    try:
        with patch("spawn_auditor.invoke_agent"), \
             patch("spawn_auditor.os.makedirs"), \
             patch("spawn_auditor.os.chdir"), \
             patch("spawn_auditor.os.path.exists", return_value=True), \
             patch("spawn_auditor.open", create=True), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("agent_driver.notify_channel"), \
             patch("utils_api_key.setup_spawner_api_key"):
            spawn_auditor.main()
    except SystemExit as e:
        if e.code == 1:
            pytest.fail("spawn_auditor exited fatally, meaning startup validation failed unexpectedly")
            
@patch("spawn_auditor.config")
@patch("sys.argv", ["/invalid_dir/spawn_auditor.py", "--prd-file", "dummy", "--workdir", "dummy", "--channel", "dummy"])
def test_spawn_auditor_startup_validation_rejects_invalid_dir(mock_config):
    mock_config.SDLC_RUNTIME_DIR = "/custom_runtime_dir"
    mock_config.DEFAULT_LLM_ENGINE = "gemini"
    import spawn_auditor
    with patch("handoff_prompter.HandoffPrompter.get_prompt", return_value="failed"), \
         patch("utils_api_key.setup_spawner_api_key"):
        with pytest.raises(SystemExit) as e:
            spawn_auditor.main()
        assert e.value.code == 1

# --- Auditor Result-Source Hotfix Tests ---

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_file_first_success(mock_invoke_agent, mock_handshake, mock_notify, capsys):
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
            prd_file = f.name
            
        os.environ["SDLC_RUN_DIR"] = tmpdir
        os.environ["SDLC_TEST_MODE"] = "false"
        
        # Write canonical verdict file
        canonical_file = os.path.join(tmpdir, "auditor_verdict.json")
        with open(canonical_file, "w") as f_out:
            json.dump({"status": "APPROVED", "comments": "File approved"}, f_out)
            
        # Mock stdout as non-JSON
        mock_result = MagicMock()
        mock_result.stdout = "Here is some conversational text without JSON."
        mock_invoke_agent.return_value = mock_result
        
        with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", tmpdir, "--channel", "test_channel"]):
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0
            
        captured = capsys.readouterr()
        assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out
        mock_notify.assert_any_call("test_channel", "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": prd_file})
        os.remove(prd_file)

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_file_first_rejection(mock_invoke_agent, mock_handshake, mock_notify, capsys):
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
            prd_file = f.name
            
        os.environ["SDLC_RUN_DIR"] = tmpdir
        os.environ["SDLC_TEST_MODE"] = "false"
        
        canonical_file = os.path.join(tmpdir, "auditor_verdict.json")
        with open(canonical_file, "w") as f_out:
            json.dump({"status": "REJECTED", "comments": "File rejected"}, f_out)
            
        mock_result = MagicMock()
        mock_result.stdout = "Conversational text without JSON."
        mock_invoke_agent.return_value = mock_result
        
        with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", tmpdir, "--channel", "test_channel"]):
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0
            
        captured = capsys.readouterr()
        assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
        os.remove(prd_file)

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_legacy_stdout_fallback(mock_invoke_agent, mock_handshake, mock_notify, capsys):
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
            prd_file = f.name
            
        os.environ["SDLC_RUN_DIR"] = tmpdir
        os.environ["SDLC_TEST_MODE"] = "false"
        
        # DO NOT write canonical verdict file
        
        mock_result = MagicMock()
        mock_result.stdout = '```json\n{"status": "APPROVED", "comments": "Stdout fallback"}\n```'
        mock_invoke_agent.return_value = mock_result
        
        with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", tmpdir, "--channel", "test_channel"]):
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0
            
        captured = capsys.readouterr()
        assert "[WARNING] Canonical verdict file missing or invalid, falling back to stdout parsing" in captured.out
        assert "[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD." in captured.out
        os.remove(prd_file)

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_conflicting_stdout_and_file(mock_invoke_agent, mock_handshake, mock_notify, capsys):
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
            prd_file = f.name
            
        os.environ["SDLC_RUN_DIR"] = tmpdir
        os.environ["SDLC_TEST_MODE"] = "false"
        
        canonical_file = os.path.join(tmpdir, "auditor_verdict.json")
        with open(canonical_file, "w") as f_out:
            json.dump({"status": "REJECTED", "comments": "File says reject"}, f_out)
            
        mock_result = MagicMock()
        # Stdout says APPROVED!
        mock_result.stdout = '{"status": "APPROVED"}'
        mock_invoke_agent.return_value = mock_result
        
        with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", tmpdir, "--channel", "test_channel"]):
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0
            
        captured = capsys.readouterr()
        assert "Conflict detected: canonical file says REJECTED but stdout says APPROVED. Using file verdict." in captured.out
        assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
        os.remove(prd_file)

@patch("agent_driver.notify_channel")
@patch("agent_driver.send_ignition_handshake")
@patch("spawn_auditor.invoke_agent")
def test_auditor_missing_file_invalid_stdout(mock_invoke_agent, mock_handshake, mock_notify, capsys):
    import tempfile
    import json
    with tempfile.TemporaryDirectory() as tmpdir:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"1. Context & Problem\n2. Requirements & User Stories\n3. Architecture & Technical Strategy\n4. Acceptance Criteria\n5. Overall Test Strategy\n6. Framework Modifications\n7. Hardcoded Content")
            prd_file = f.name
            
        os.environ["SDLC_RUN_DIR"] = tmpdir
        os.environ["SDLC_TEST_MODE"] = "false"
        
        # Missing file, invalid stdout
        mock_result = MagicMock()
        mock_result.stdout = "Nothing to see here."
        mock_invoke_agent.return_value = mock_result
        
        with patch.object(sys, "argv", ["spawn_auditor.py", "--enable-exec-from-workspace", "--prd-file", prd_file, "--workdir", tmpdir, "--channel", "test_channel"]):
            with pytest.raises(SystemExit) as e:
                spawn_auditor.main()
            assert e.value.code == 0
            
        captured = capsys.readouterr()
        # UNKNOWN status falls through to REJECTED logic
        assert "[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD." in captured.out
        os.remove(prd_file)
