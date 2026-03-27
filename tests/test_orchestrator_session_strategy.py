import os
import sys
import subprocess
import pytest
from unittest.mock import patch, MagicMock

# Assuming orchestrator is importable or we can test it using subprocess / module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

def test_invalid_strategy():
    result = subprocess.run(
        [sys.executable, "scripts/orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--coder-session-strategy", "invalid-strategy"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "argument --coder-session-strategy: invalid choice: 'invalid-strategy'" in result.stderr

def test_missing_workdir():
    result = subprocess.run(
        [sys.executable, "scripts/orchestrator.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "the following arguments are required: --workdir" in result.stderr

# We need to test the logic of teardown_coder_session.
# Let's mock the main loop and verify the calls.
@patch('orchestrator.teardown_coder_session')
@patch('orchestrator.subprocess.run')
@patch('orchestrator.safe_git_checkout')
@patch('orchestrator.glob.glob')
@patch('orchestrator.os.path.exists')
@patch('orchestrator.set_pr_status')
@patch('orchestrator.open')
def test_always_strategy(mock_open, mock_set_pr_status, mock_exists, mock_glob, mock_safe_git_checkout, mock_subprocess_run, mock_teardown):
    import orchestrator
    
    # Setup mocks
    mock_exists.return_value = True
    mock_glob.side_effect = [
        ["dummy_pr.md"], # For checking if has_md
        ["dummy_pr.md"], # For the main loop
    ]
    
    mock_open.return_value.__enter__.return_value.read.return_value = "status: in_progress\n"
    
    # We want it to run one loop and then exit. Let's make coder_result fail to trigger state 5, then exit.
    def mock_run(*args, **kwargs):
        if "spawn_coder.py" in args[0]:
            mock_run.coder_calls += 1
            if mock_run.coder_calls > 1:
                sys.exit(0) # Stop the loop
            return MagicMock(returncode=1) # Fail, triggers State 5
        return MagicMock(returncode=0)
        
    mock_run.coder_calls = 0
    mock_subprocess_run.side_effect = mock_run
    
    with patch('sys.argv', ['orchestrator.py', '--enable-exec-from-workspace', '--workdir', '.', '--prd-file', 'dummy.md', '--coder-session-strategy', 'always', '--max-runs', '1']):
        try:
            orchestrator.main()
        except SystemExit:
            pass
            
    # Under 'always' it should be called inside the retry loop (before spawn_coder.py)
    # and maybe conditionally in State 5 if on-escalation (but we chose 'always', so State 5 won't call it).
    # Wait, the prompt said "on-escalation: Call teardown_coder_session(workdir) upon entering State 5". Does that mean ONLY on escalation?
    # Yes, our code does: `if args.coder_session_strategy == "on-escalation": teardown_coder_session(workdir)` inside State 5.
    # So for 'always', it's called in State 3.
    mock_teardown.assert_called_with(os.path.abspath("."))
    
@patch('orchestrator.teardown_coder_session')
@patch('orchestrator.subprocess.run')
@patch('orchestrator.safe_git_checkout')
@patch('orchestrator.glob.glob')
@patch('orchestrator.os.path.exists')
@patch('orchestrator.set_pr_status')
@patch('orchestrator.open')
def test_per_pr_strategy(mock_open, mock_set_pr_status, mock_exists, mock_glob, mock_safe_git_checkout, mock_subprocess_run, mock_teardown):
    import orchestrator
    
    mock_exists.return_value = True
    mock_glob.side_effect = [
        ["dummy_pr.md"],
        ["dummy_pr.md"],
    ]
    
    mock_open.return_value.__enter__.return_value.read.return_value = "status: in_progress\n"
    
    with patch('sys.argv', ['orchestrator.py', '--enable-exec-from-workspace', '--workdir', '.', '--prd-file', 'dummy.md', '--coder-session-strategy', 'per-pr', '--max-runs', '1']):
        try:
            orchestrator.main()
        except SystemExit:
            pass
            
    mock_teardown.assert_called_with(os.path.abspath("."))

@patch('orchestrator.teardown_coder_session')
@patch('orchestrator.subprocess.run')
@patch('orchestrator.safe_git_checkout')
@patch('orchestrator.glob.glob')
@patch('orchestrator.os.path.exists')
@patch('orchestrator.set_pr_status')
@patch('orchestrator.open')
def test_on_escalation_strategy(mock_open, mock_set_pr_status, mock_exists, mock_glob, mock_safe_git_checkout, mock_subprocess_run, mock_teardown):
    import orchestrator
    
    mock_exists.return_value = True
    mock_glob.side_effect = [
        ["dummy_pr.md"],
        ["dummy_pr.md"],
    ]
    
    mock_open.return_value.__enter__.return_value.read.return_value = "status: in_progress\n"
    
    def mock_run(*args, **kwargs):
        if "spawn_coder.py" in args[0]:
            return MagicMock(returncode=1) # Fail to trigger escalation
        return MagicMock(returncode=0)
        
    mock_subprocess_run.side_effect = mock_run
    
    with patch('sys.argv', ['orchestrator.py', '--enable-exec-from-workspace', '--workdir', '.', '--prd-file', 'dummy.md', '--coder-session-strategy', 'on-escalation', '--max-runs', '1']):
        try:
            orchestrator.main()
        except SystemExit:
            pass
            
    mock_teardown.assert_called_with(os.path.abspath("."))
