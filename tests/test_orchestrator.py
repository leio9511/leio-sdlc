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
    with patch('orchestrator.teardown_coder_session'), \
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
    with patch('orchestrator.teardown_coder_session') as mock_teardown, \
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
    with patch('orchestrator.teardown_coder_session'), \
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
