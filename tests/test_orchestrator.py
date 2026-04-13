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
