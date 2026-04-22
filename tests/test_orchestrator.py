import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator

@pytest.fixture
def mock_workdir():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, '.git'))
        yield temp_dir

def test_orchestrator_json_retry_framework_success(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), patch('orchestrator.teardown_coder_session'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel'), \
         patch('orchestrator.glob.glob') as mock_glob, \
         patch('orchestrator.set_pr_status'), \
         patch('orchestrator.extract_and_parse_json') as mock_extract:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
            mock_res.returncode = 0
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        
        mock_dpopen.return_value.returncode = 0
        pr_file = os.path.join(mock_workdir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")
            
        def dummy_glob(pattern, recursive=False):
            return [] if ".coder_session" in pattern else [pr_file]
        mock_glob.side_effect = dummy_glob
        
        # Simulate parsing success on the 2nd attempt
        mock_extract.side_effect = [ValueError("Bad JSON"), {"overall_assessment": "EXCELLENT"}]
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        assert mock_extract.call_count == 2

def test_orchestrator_json_retry_framework_failure(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), patch('orchestrator.teardown_coder_session') as mock_teardown, \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel'), \
         patch('orchestrator.glob.glob') as mock_glob, \
         patch('orchestrator.get_pr_slice_depth', return_value=0), \
         patch('orchestrator.set_pr_status'), \
         patch('orchestrator.extract_and_parse_json') as mock_extract:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
            mock_res.returncode = 0
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        
        mock_dpopen.return_value.returncode = 0
        pr_file = os.path.join(mock_workdir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")
            
        def dummy_glob(pattern, recursive=False):
            if ".coder_session" in pattern or mock_glob.call_count > 5:
                return []
            return [pr_file]
        mock_glob.side_effect = dummy_glob
        
        # Simulate parsing failure 3 times then something else
        mock_extract.side_effect = [ValueError("Bad JSON")] * 10
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        assert mock_extract.call_count >= 3
        # Should trigger Red Path reset, meaning teardown_coder_session is called
        assert mock_teardown.call_count > 0

def test_orchestrator_system_alert_invocation(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), patch('orchestrator.teardown_coder_session'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel'), \
         patch('orchestrator.glob.glob') as mock_glob, \
         patch('orchestrator.set_pr_status'), \
         patch('orchestrator.extract_and_parse_json') as mock_extract:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
            mock_res.returncode = 0
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        
        mock_dpopen.return_value.returncode = 0
        pr_file = os.path.join(mock_workdir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")
            
        def dummy_glob(pattern, recursive=False):
            return [] if ".coder_session" in pattern else [pr_file]
        mock_glob.side_effect = dummy_glob
        
        # Simulate parsing success on the 2nd attempt
        mock_extract.side_effect = [ValueError("Bad JSON"), {"overall_assessment": "EXCELLENT"}]
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        assert mock_extract.call_count == 2
        
        # Check dpopen calls. The first one is Planner, then Coder, then Reviewer (Attempt 1), then Reviewer (Attempt 2 with system alert)
        dpopen_calls = mock_dpopen.call_args_list
        system_alert_calls = [call for call in dpopen_calls if "spawn_reviewer.py" in " ".join(call[0][0]) and "--system-alert" in call[0][0]]
        
        assert len(system_alert_calls) > 0
        sys_alert_arg = system_alert_calls[0][0][0]
        assert "SYSTEM ALERT: Your previous output could not be parsed as valid JSON. Please return ONLY a strict JSON object matching the required schema. No markdown formatting, no conversational text." in sys_alert_arg

def test_parse_review_verdict_success():
    content = '{"overall_assessment": "EXCELLENT"}'
    assert orchestrator.parse_review_verdict(content) == "APPROVED"

def test_parse_review_verdict_failure():
    content = 'invalid json'
    assert orchestrator.parse_review_verdict(content) is None

@patch('orchestrator.drun')
@patch('orchestrator.dpopen')
@patch('orchestrator.validate_prd_is_committed')
@patch('orchestrator.acquire_global_locks', return_value=([], []))
@patch('orchestrator.parse_affected_projects', return_value=[])
@patch('git_utils.check_git_boundary')
@patch('orchestrator.notify_channel')
def test_orchestrator_cli_engine_args(mock_notify, mock_check, mock_parse, mock_acquire, mock_validate, mock_dpopen, mock_drun, mock_workdir):
    def dummy_drun(cmd, *args, **kwargs):
        mock_res = MagicMock()
        mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
        mock_res.returncode = 0
        return mock_res
    mock_drun.side_effect = dummy_drun

    with patch.dict(os.environ, {}, clear=True):
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--engine', 'gemini', '--model', 'my-model', '--test-sleep']):
                orchestrator.main()
        except SystemExit as e:
            pass
        assert os.environ.get("LLM_DRIVER") == "gemini"
        assert os.environ.get("SDLC_MODEL") == "my-model"

@patch('orchestrator.drun')
@patch('orchestrator.dpopen')
@patch('orchestrator.validate_prd_is_committed')
@patch('orchestrator.acquire_global_locks', return_value=([], []))
@patch('orchestrator.parse_affected_projects', return_value=[])
@patch('git_utils.check_git_boundary')
@patch('orchestrator.notify_channel')
def test_orchestrator_environment_fallback(mock_notify, mock_check, mock_parse, mock_acquire, mock_validate, mock_dpopen, mock_drun, mock_workdir):
    def dummy_drun(cmd, *args, **kwargs):
        mock_res = MagicMock()
        mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
        mock_res.returncode = 0
        return mock_res
    mock_drun.side_effect = dummy_drun

    with patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_MODEL": "test-fallback"}):
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--test-sleep']):
                orchestrator.main()
        except SystemExit as e:
            pass
        assert os.environ.get("LLM_DRIVER") == "gemini"
        assert os.environ.get("SDLC_MODEL") == "test-fallback"


@patch('utils_api_key.assign_gemini_api_key')
def test_get_env_with_gemini_key(mock_assign_key):
    mock_assign_key.return_value = "mocked_key"
    gemini_api_keys = ["key1", "key2"]
    
    with patch.dict(os.environ, {}, clear=True):
        env = orchestrator.get_env_with_gemini_key("my_session", gemini_api_keys, "/global/dir")
        assert env.get("GEMINI_API_KEY") == "mocked_key"
        mock_assign_key.assert_called_once_with(
            "my_session", 
            {"gemini_api_keys": gemini_api_keys}, 
            os.path.join("/global/dir", ".sdlc_runs", ".session_keys.json")
        )

import json

def test_uat_recovery_spawns_planner(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "NEEDS_FIX",
                        "verification_details": [
                            {"status": "MISSING", "detail": "test"}
                        ]
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        # Prevent actually calling continue in the infinite loop by throwing an exception
        # or limiting loops, but since we test the break we'll mock dpopen to raise SystemExit after the first planner run
        def dummy_dpopen(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "spawn_planner.py" in " ".join(cmd) and "--replan-uat-failures" in " ".join(cmd):
                raise SystemExit(0)  # Stop orchestrator here for test
            return mock_proc
        mock_dpopen.side_effect = dummy_dpopen
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        # Check that dpopen was called for spawn_planner.py with replan
        dpopen_calls = mock_dpopen.call_args_list
        planner_calls = [call for call in dpopen_calls if "spawn_planner.py" in " ".join(call[0][0]) and "--replan-uat-failures" in " ".join(call[0][0])]
        assert len(planner_calls) > 0

def test_uat_recovery_circuit_breaker(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        # write a config that sets max_uat_recovery_attempts to 0
        config_dir = os.path.join(mock_workdir, "config")
        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, "sdlc_config.json"), "w") as f:
            json.dump({"max_uat_recovery_attempts": 0}, f)
            
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "NEEDS_FIX",
                        "verification_details": [
                            {"status": "MISSING", "detail": "test"}
                        ]
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit as e:
            assert e.code == 1
            
        state_file = os.path.join(mock_workdir, "STATE.md")
        assert os.path.exists(state_file)
        with open(state_file, "r") as f:
            content = f.read()
            assert "UAT_BLOCKED" in content
            
        # Check correct slack alert sent
        notify_calls = mock_notify.call_args_list
        alert_sent = any("UAT 补救次数已达上限" in call[0][1] for call in notify_calls)
        assert alert_sent

def test_uat_system_error_circuit_breaker(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output - BAD JSON
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    f.write("invalid json string")
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit as e:
            assert e.code == 1
            
        state_file = os.path.join(mock_workdir, "STATE.md")
        assert os.path.exists(state_file)
        with open(state_file, "r") as f:
            content = f.read()
            assert "UAT_ERROR" in content
            
        # Check correct slack alert sent
        notify_calls = mock_notify.call_args_list
        alert_sent = any("UAT Agent 发生系统级错误" in call[0][1] for call in notify_calls)
        assert alert_sent
        
        # Ensure it retried 3 times
        drun_calls = mock_drun.call_args_list
        verifier_calls = [call for call in drun_calls if "spawn_verifier.py" in " ".join(call[0][0])]
        assert len(verifier_calls) == 3

# PRD Trigger_UAT_Recovery_For_Partial_Findings: Ensure PARTIAL findings trigger recovery
def test_uat_recovery_triggered_by_partial(mock_workdir):

    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output with PARTIAL
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "NEEDS_FIX",
                        "verification_details": [
                            {"status": "PARTIAL", "detail": "test partial"}
                        ]
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        def dummy_dpopen(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "spawn_planner.py" in " ".join(cmd) and "--replan-uat-failures" in " ".join(cmd):
                raise SystemExit(0)  # Stop orchestrator here for test
            return mock_proc
        mock_dpopen.side_effect = dummy_dpopen
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        dpopen_calls = mock_dpopen.call_args_list
        planner_calls = [call for call in dpopen_calls if "spawn_planner.py" in " ".join(call[0][0]) and "--replan-uat-failures" in " ".join(call[0][0])]
        assert len(planner_calls) > 0

def test_uat_recovery_still_triggered_by_missing(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output with MISSING
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "NEEDS_FIX",
                        "verification_details": [
                            {"status": "MISSING", "detail": "test missing"}
                        ]
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        def dummy_dpopen(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "spawn_planner.py" in " ".join(cmd) and "--replan-uat-failures" in " ".join(cmd):
                raise SystemExit(0)
            return mock_proc
        mock_dpopen.side_effect = dummy_dpopen
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        dpopen_calls = mock_dpopen.call_args_list
        planner_calls = [call for call in dpopen_calls if "spawn_planner.py" in " ".join(call[0][0]) and "--replan-uat-failures" in " ".join(call[0][0])]
        assert len(planner_calls) > 0

def test_uat_no_recovery_on_pass(mock_workdir):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output with PASS
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "PASS",
                        "verification_details": []
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        mock_dpopen.return_value.returncode = 0
        
        exit_code = None
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit as e:
            exit_code = e.code
            
        assert exit_code == 0
        
        dpopen_calls = mock_dpopen.call_args_list
        planner_calls = [call for call in dpopen_calls if "spawn_planner.py" in " ".join(call[0][0]) and "--replan-uat-failures" in " ".join(call[0][0])]
        assert len(planner_calls) == 0

def test_uat_manager_handoff_wording(mock_workdir, capsys):
    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir]), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob:
         
        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "get_next_pr.py" in cmd[0] if len(cmd) > 1 else False:
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0
            
            # Mock UAT verifier output with NEEDS_FIX but NO MISSING/PARTIAL items (to trigger fallback)
            if isinstance(cmd, list) and "spawn_verifier.py" in " ".join(cmd):
                uat_out_file = [arg for arg in cmd if arg.endswith("uat_report.json")][0]
                with open(uat_out_file, "w") as f:
                    json.dump({
                        "status": "NEEDS_FIX",
                        "verification_details": [
                            {"status": "OTHER", "detail": "something else"}
                        ]
                    }, f)
            return mock_res
            
        mock_drun.side_effect = dummy_drun
        
        target_project_name = os.path.basename(os.path.abspath(mock_workdir))
        job_dir = os.path.join(mock_workdir, ".sdlc_runs", target_project_name, "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: closed\n---\n")

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [pr_file]
            return []
        mock_glob.side_effect = dummy_glob
        
        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--enable-exec-from-workspace', '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass
            
        captured = capsys.readouterr()
        assert "Read uat_report.json, summarize the unmet findings to the Boss, and ask whether to append a hotfix or redo." in captured.out
