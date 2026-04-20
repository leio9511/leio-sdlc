import os
import sys
import tempfile
import pytest
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator

@pytest.fixture
def mock_workdir():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, '.git'))
        yield temp_dir

@patch('git_utils.check_git_boundary')
@patch('orchestrator.SanityContext.perform_healthy_check')
@patch('orchestrator.validate_prd_is_committed')
@patch('orchestrator.notify_channel')
@patch('orchestrator.drun')
@patch('orchestrator.dpopen')
@patch('sys.exit')
@patch('orchestrator.extract_and_parse_json')
def test_uat_missing_within_limit(mock_extract, mock_exit, mock_dpopen, mock_drun, mock_notify, mock_validate, mock_sanity, mock_git_bound, mock_workdir):
    sys.argv = ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--max-prs-to-process', '1']
    os.environ["SDLC_TEST_MODE"] = "true"
    

    def side_effect_drun(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if "get_next_pr.py" in cmd or ("get_next_pr.py" in str(cmd)):
            res.stdout = "[QUEUE_EMPTY]"
        else:
            res.stdout = ""
            if "spawn_verifier.py" in str(cmd):
                # recreate the file
                uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
                os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
                with open(uat_report_path, "w") as f:
                    f.write("{}")
        return res
    mock_drun.side_effect = side_effect_drun

    uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
    os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
    with open(uat_report_path, "w") as f:
        f.write("{}")
        
    job_dir = os.path.dirname(uat_report_path)
    with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
        f.write("status: closed")

    config_path = os.path.join(mock_workdir, "config", "sdlc_config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump({"max_uat_recovery_attempts": 5}, f)

    mock_extract.return_value = {"status": "NEEDS_FIX", "missing": ["Some missing req"]}

    with patch('orchestrator.glob.glob') as mock_glob:
        def mock_glob_side_effect(path, *args, **kwargs):
            if "PR_*" in path or "*.md" in path:
                if "job_dir" in path or "dummy_prd" in path:
                    return [os.path.join(job_dir, "PR_001.md")]
            return []
        mock_glob.side_effect = mock_glob_side_effect

        try:
            orchestrator.main()
        except BaseException:
            pass

    planner_called = False
    for call in mock_dpopen.call_args_list:
        cmd = call[0][0]
        if "spawn_planner.py" in str(cmd) and "--replan-uat-failures" in str(cmd):
            planner_called = True
    assert planner_called


@patch('git_utils.check_git_boundary')
@patch('orchestrator.SanityContext.perform_healthy_check')
@patch('orchestrator.validate_prd_is_committed')
@patch('orchestrator.notify_channel')
@patch('orchestrator.drun')
@patch('orchestrator.dpopen')
@patch('sys.exit')
@patch('orchestrator.extract_and_parse_json')
def test_uat_missing_limit_exceeded(mock_extract, mock_exit, mock_dpopen, mock_drun, mock_notify, mock_validate, mock_sanity, mock_git_bound, mock_workdir):
    sys.argv = ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--max-prs-to-process', '1']
    os.environ["SDLC_TEST_MODE"] = "true"

    def side_effect_drun(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if "get_next_pr.py" in cmd or ("get_next_pr.py" in str(cmd)):
            res.stdout = "[QUEUE_EMPTY]"
        else:
            res.stdout = ""
            if "spawn_verifier.py" in str(cmd):
                # recreate the file
                uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
                os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
                with open(uat_report_path, "w") as f:
                    f.write("{}")
        return res
    mock_drun.side_effect = side_effect_drun

    uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
    os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
    with open(uat_report_path, "w") as f:
        f.write("{}")

    job_dir = os.path.dirname(uat_report_path)
    with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
        f.write("status: closed")

    config_path = os.path.join(mock_workdir, "config", "sdlc_config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump({"max_uat_recovery_attempts": 0}, f)

    mock_extract.return_value = {"status": "NEEDS_FIX", "missing": ["Some missing req"]}

    with patch('orchestrator.glob.glob') as mock_glob:
        def mock_glob_side_effect(path, *args, **kwargs):
            if "PR_*" in path or "*.md" in path:
                if "job_dir" in path or "dummy_prd" in path:
                    return [os.path.join(job_dir, "PR_001.md")]
            return []
        mock_glob.side_effect = mock_glob_side_effect
        
        original_open = open
        def mock_open_impl(file, mode='r', *args, **kwargs):
            if 'STATE.md' in str(file) and mode == 'w':
                mock_handle = MagicMock()
                mock_handle.__enter__.return_value = mock_handle
                mock_open_impl.state_writes = getattr(mock_open_impl, 'state_writes', [])
                def write_hook(data):
                    mock_open_impl.state_writes.append(data)
                mock_handle.write.side_effect = write_hook
                return mock_handle
            return original_open(file, mode, *args, **kwargs)

        with patch('builtins.open', side_effect=mock_open_impl) as mock_open:
            with patch('json.load', return_value={"max_uat_recovery_attempts": 0}):
                try:
                    orchestrator.main()
                except BaseException:
                    pass

            write_blocked = False
            if getattr(mock_open_impl, 'state_writes', None):
                for data in mock_open_impl.state_writes:
                    if "UAT_BLOCKED" in data:
                        write_blocked = True
            assert write_blocked


@patch('git_utils.check_git_boundary')
@patch('orchestrator.SanityContext.perform_healthy_check')
@patch('orchestrator.validate_prd_is_committed')
@patch('orchestrator.notify_channel')
@patch('orchestrator.drun')
@patch('orchestrator.dpopen')
@patch('sys.exit')
@patch('orchestrator.extract_and_parse_json')
def test_uat_circuit_breaker(mock_extract, mock_exit, mock_dpopen, mock_drun, mock_notify, mock_validate, mock_sanity, mock_git_bound, mock_workdir):
    sys.argv = ['orchestrator.py', '--workdir', mock_workdir, '--prd-file', 'dummy_prd.md', '--force-replan', 'false', '--channel', 'test-channel', '--max-prs-to-process', '1']
    os.environ["SDLC_TEST_MODE"] = "true"

    def side_effect_drun(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if "get_next_pr.py" in cmd or ("get_next_pr.py" in str(cmd)):
            res.stdout = "[QUEUE_EMPTY]"
        else:
            res.stdout = ""
            if "spawn_verifier.py" in str(cmd):
                # recreate the file
                uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
                os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
                with open(uat_report_path, "w") as f:
                    f.write("{}")
        return res
    mock_drun.side_effect = side_effect_drun

    uat_report_path = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd", "uat_report.json")
    os.makedirs(os.path.dirname(uat_report_path), exist_ok=True)
    with open(uat_report_path, "w") as f:
        f.write("{}")

    job_dir = os.path.dirname(uat_report_path)
    with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
        f.write("status: closed")

    config_path = os.path.join(mock_workdir, "config", "sdlc_config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump({"max_uat_recovery_attempts": 0}, f)

    mock_extract.side_effect = Exception("malformed json")

    with patch('orchestrator.glob.glob') as mock_glob:
        def mock_glob_side_effect(path, *args, **kwargs):
            if "PR_*" in path or "*.md" in path:
                if "job_dir" in path or "dummy_prd" in path:
                    return [os.path.join(job_dir, "PR_001.md")]
            return []
        mock_glob.side_effect = mock_glob_side_effect

        original_open = open
        def mock_open_impl(file, mode='r', *args, **kwargs):
            if 'STATE.md' in str(file) and mode == 'w':
                mock_handle = MagicMock()
                mock_handle.__enter__.return_value = mock_handle
                mock_open_impl.state_writes = getattr(mock_open_impl, 'state_writes', [])
                def write_hook(data):
                    mock_open_impl.state_writes.append(data)
                mock_handle.write.side_effect = write_hook
                return mock_handle
            return original_open(file, mode, *args, **kwargs)

        with patch('builtins.open', side_effect=mock_open_impl) as mock_open:
            try:
                orchestrator.main()
            except BaseException:
                pass

            write_blocked = False
            if getattr(mock_open_impl, 'state_writes', None):
                for data in mock_open_impl.state_writes:
                    if "UAT_BLOCKED" in data:
                        write_blocked = True
            assert write_blocked
