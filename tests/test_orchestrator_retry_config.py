import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


@pytest.fixture
def retry_config_workspace(tmp_path):
    sdlc_root = tmp_path / "sdlc_root"
    global_dir = tmp_path / "global_dir"
    _write_json(
        sdlc_root / "config" / "sdlc_config.json.template",
        {
            "YELLOW_RETRY_LIMIT": 3,
            "RED_RETRY_LIMIT": 2,
            "max_uat_recovery_attempts": 5,
        },
    )
    return sdlc_root, global_dir


def test_retry_config_keeps_global_values_when_local_config_absent(retry_config_workspace):
    sdlc_root, global_dir = retry_config_workspace
    _write_json(
        sdlc_root / "config" / "sdlc_config.json",
        {
            "YELLOW_RETRY_LIMIT": 8,
            "RED_RETRY_LIMIT": 7,
            "max_uat_recovery_attempts": 6,
        },
    )

    resolved = orchestrator.resolve_retry_recovery_config(str(sdlc_root), str(global_dir))

    assert resolved["YELLOW_RETRY_LIMIT"] == 8
    assert resolved["RED_RETRY_LIMIT"] == 7
    assert resolved["max_uat_recovery_attempts"] == 6


def test_retry_config_local_overrides_global_when_present(retry_config_workspace):
    sdlc_root, global_dir = retry_config_workspace
    _write_json(
        sdlc_root / "config" / "sdlc_config.json",
        {
            "YELLOW_RETRY_LIMIT": 8,
            "RED_RETRY_LIMIT": 7,
            "max_uat_recovery_attempts": 6,
        },
    )
    _write_json(
        global_dir / "config" / "sdlc_config.json",
        {
            "YELLOW_RETRY_LIMIT": 4,
            "max_uat_recovery_attempts": 1,
        },
    )

    resolved = orchestrator.resolve_retry_recovery_config(str(sdlc_root), str(global_dir))

    assert resolved["YELLOW_RETRY_LIMIT"] == 4
    assert resolved["RED_RETRY_LIMIT"] == 7
    assert resolved["max_uat_recovery_attempts"] == 1


def test_retry_config_missing_local_does_not_restore_defaults(retry_config_workspace):
    sdlc_root, global_dir = retry_config_workspace
    _write_json(
        sdlc_root / "config" / "sdlc_config.json",
        {
            "YELLOW_RETRY_LIMIT": 9,
            "RED_RETRY_LIMIT": 8,
            "max_uat_recovery_attempts": 0,
        },
    )

    resolved = orchestrator.resolve_retry_recovery_config(str(sdlc_root), str(global_dir))

    assert resolved["YELLOW_RETRY_LIMIT"] == 9
    assert resolved["RED_RETRY_LIMIT"] == 8
    assert resolved["max_uat_recovery_attempts"] == 0
    assert resolved["YELLOW_RETRY_LIMIT"] != 3
    assert resolved["RED_RETRY_LIMIT"] != 2
    assert resolved["max_uat_recovery_attempts"] != 5


def test_orchestrator_uat_recovery_uses_resolved_global_limit_without_local_config(tmp_path):
    workdir = tmp_path / "workdir"
    global_dir = tmp_path / "global_dir"
    sdlc_root = tmp_path / "sdlc_root"
    workdir.mkdir()
    (workdir / ".git").mkdir()
    _write_json(
        sdlc_root / "config" / "sdlc_config.json.template",
        {
            "YELLOW_RETRY_LIMIT": 3,
            "RED_RETRY_LIMIT": 2,
            "max_uat_recovery_attempts": 5,
        },
    )
    _write_json(
        sdlc_root / "config" / "sdlc_config.json",
        {"max_uat_recovery_attempts": 0},
    )

    target_project_name = os.path.basename(os.path.abspath(workdir))
    job_dir = global_dir / ".sdlc_runs" / target_project_name / "dummy_prd"
    job_dir.mkdir(parents=True)
    pr_file = job_dir / "PR_001_test.md"
    pr_file.write_text("---\nstatus: closed\n---\n")

    with patch.object(orchestrator, '__file__', str(sdlc_root / "scripts" / "orchestrator.py")), \
         patch('orchestrator.SanityContext.perform_healthy_check'), \
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
            if isinstance(cmd, list) and "get_next_pr.py" in " ".join(cmd):
                mock_res.stdout = "[QUEUE_EMPTY]\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            else:
                mock_res.stdout = ""
            mock_res.returncode = 0

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

        def dummy_glob(pattern, recursive=False):
            if "PR_*.md" in pattern or "*.md" in pattern:
                return [str(pr_file)]
            return []

        mock_glob.side_effect = dummy_glob
        mock_dpopen.return_value.returncode = 0

        with pytest.raises(SystemExit) as exc:
            with patch('sys.argv', [
                'orchestrator.py',
                '--workdir', str(workdir),
                '--prd-file', 'dummy_prd.md',
                '--force-replan', 'false',
                '--channel', 'test-channel',
                '--enable-exec-from-workspace',
                '--global-dir', str(global_dir),
                '--max-prs-to-process', '1',
            ]):
                orchestrator.main()

        assert exc.value.code == 1
        planner_calls = [
            call for call in mock_dpopen.call_args_list
            if "spawn_planner.py" in " ".join(call[0][0]) and "--replan-uat-failures" in " ".join(call[0][0])
        ]
        assert planner_calls == []
        state_file = workdir / "STATE.md"
        assert state_file.read_text() == "UAT_BLOCKED\n"
        assert any("UAT 补救次数已达上限" in call[0][1] for call in mock_notify.call_args_list)


def test_orchestrator_preflight_retry_uses_resolved_yellow_limit(tmp_path):
    workdir = tmp_path / "workdir"
    global_dir = tmp_path / "global_dir"
    sdlc_root = tmp_path / "sdlc_root"
    workdir.mkdir()
    (workdir / ".git").mkdir()
    (workdir / "preflight.sh").write_text("#!/bin/bash\nexit 1")
    _write_json(
        sdlc_root / "config" / "sdlc_config.json.template",
        {
            "YELLOW_RETRY_LIMIT": 3,
            "RED_RETRY_LIMIT": 2,
            "max_uat_recovery_attempts": 5,
        },
    )
    _write_json(
        sdlc_root / "config" / "sdlc_config.json",
        {"YELLOW_RETRY_LIMIT": 1},
    )

    target_project_name = os.path.basename(os.path.abspath(workdir))
    job_dir = global_dir / ".sdlc_runs" / target_project_name / "dummy_prd"
    job_dir.mkdir(parents=True)
    pr_file = job_dir / "PR_001_test.md"
    pr_file.write_text("status: in_progress\n")

    with patch.object(orchestrator, '__file__', str(sdlc_root / "scripts" / "orchestrator.py")), \
         patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('orchestrator.teardown_coder_session'), \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob, \
         patch('orchestrator.set_pr_status'), \
         patch('orchestrator.get_pr_slice_depth', return_value=2):

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list) and "preflight.sh" in " ".join(cmd):
                mock_res.returncode = 1
                mock_res.stdout = "Preflight failed error"
                mock_res.stderr = ""
            elif isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
                mock_res.returncode = 0
            else:
                mock_res.stdout = ""
                mock_res.stderr = ""
                mock_res.returncode = 0
            return mock_res

        mock_drun.side_effect = dummy_drun

        def dummy_glob(pattern, recursive=False):
            return [] if ".coder_session" in pattern else [str(pr_file)]

        mock_glob.side_effect = dummy_glob
        mock_dpopen.return_value.returncode = 0

        try:
            with patch('sys.argv', [
                'orchestrator.py',
                '--workdir', str(workdir),
                '--prd-file', 'dummy_prd.md',
                '--force-replan', 'false',
                '--channel', 'test-channel',
                '--enable-exec-from-workspace',
                '--global-dir', str(global_dir),
                '--max-prs-to-process', '1',
            ]):
                orchestrator.main()
        except SystemExit:
            pass

        preflight_notifications = [
            call for call in mock_notify.call_args_list
            if len(call[0]) > 2 and call[0][2] == "preflight_failed"
        ]
        assert len(preflight_notifications) >= 1
        assert all(call[0][3]["limit"] == 1 for call in preflight_notifications)
        assert all("attempt 1/1" in call[0][1] for call in preflight_notifications)
        coder_system_alert_calls = [
            call for call in mock_dpopen.call_args_list
            if "spawn_coder.py" in " ".join(call[0][0]) and "--system-alert" in call[0][0]
        ]
        assert coder_system_alert_calls == []
