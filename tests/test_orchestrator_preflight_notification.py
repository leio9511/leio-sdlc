"""
PR-002: Preflight Failure Notification Tests

Tests verifying that notify_channel is called with the correct message
format when preflight.sh fails, and that control flow remains correct.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))

from planner_test_support import seed_planner_success_artifacts, seeded_job_dir_glob_side_effect

import orchestrator


@pytest.fixture
def mock_workdir_with_preflight():
    """Creates a temp workdir with .git and a dummy preflight.sh."""
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, ".git"), exist_ok=True)
        Path(os.path.join(temp_dir, "preflight.sh")).write_text(
            "#!/bin/bash\necho 'mock preflight'\n", encoding="utf-8"
        )
        yield temp_dir


def _prepare_seeded_pr(mock_workdir):
    seeded = seed_planner_success_artifacts(
        mock_workdir,
        mock_workdir,
        prd_filename="dummy_prd.md",
        pr_slice_content="status: in_progress\n",
    )
    return seeded["job_dir"], seeded["pr_file"]


def _base_drun_result(stdout="", returncode=0, stderr=""):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# Test Case 1: preflight failure sends notification
# ---------------------------------------------------------------------------
def test_preflight_failure_sends_notification(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_seeded_pr(mock_workdir)

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.teardown_coder_session"), \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.extract_and_parse_json") as mock_extract, \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
                if "preflight.sh" in cmd_str:
                    return _base_drun_result("test output", 1, "test stderr output")
                if "get_next_pr.py" in cmd_str:
                    return _base_drun_result("[QUEUE_EMPTY]\n", 0)
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun
        mock_dpopen.return_value.returncode = 0
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)
        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir",
                    mock_workdir,
                    "--prd-file",
                    "dummy_prd.md",
                    "--force-replan",
                    "false",
                    "--channel",
                    "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir",
                    mock_workdir,
                    "--max-prs-to-process",
                    "1",
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        preflight_calls = [
            c for c in mock_notify.call_args_list if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) > 0

        first_call = preflight_calls[0]
        channel = first_call[0][0]
        message = first_call[0][1]
        event_type = first_call[0][2]
        metadata = first_call[0][3]

        assert channel == "test-channel"
        assert event_type == "preflight_failed"
        assert "Preflight failed" in message
        assert "PR_001_test" in message
        assert "attempt" in message
        assert "Retrying Coder" in message
        assert metadata["pr_id"] == "PR_001_test"
        assert metadata["attempt"] == 1
        assert metadata["limit"] > 0


# ---------------------------------------------------------------------------
# Test Case 2: preflight success does NOT send notification
# ---------------------------------------------------------------------------
def test_preflight_success_does_not_send_notification(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_seeded_pr(mock_workdir)

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.teardown_coder_session"), \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.extract_and_parse_json") as mock_extract, \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
                if "preflight.sh" in cmd_str:
                    return _base_drun_result("all good", 0, "")
                if "get_next_pr.py" in cmd_str:
                    return _base_drun_result("[QUEUE_EMPTY]\n", 0)
                if "merge_code.py" in cmd_str or cmd[:2] == ["git", "checkout"] or cmd[:3] == ["git", "branch", "-D"]:
                    return _base_drun_result("", 0)
                if cmd[:3] == ["git", "reset", "--hard"] or cmd[:3] == ["git", "clean", "-fd"]:
                    return _base_drun_result("", 0)
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun
        mock_dpopen.return_value.returncode = 0
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)
        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir",
                    mock_workdir,
                    "--prd-file",
                    "dummy_prd.md",
                    "--force-replan",
                    "false",
                    "--channel",
                    "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir",
                    mock_workdir,
                    "--max-prs-to-process",
                    "1",
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        preflight_calls = [
            c for c in mock_notify.call_args_list if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) == 0

        reviewer_calls = [
            c for c in mock_notify.call_args_list if c[0][2] == "reviewer_spawned"
        ]
        assert len(reviewer_calls) > 0


# ---------------------------------------------------------------------------
# Test Case 3: preflight retry limit reached triggers state_5
# ---------------------------------------------------------------------------
def test_preflight_retry_limit_reached_triggers_state_5(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_seeded_pr(mock_workdir)
    loop_iteration = [0]

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.teardown_coder_session") as mock_teardown, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.extract_and_parse_json") as mock_extract, \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
                if "preflight.sh" in cmd_str:
                    loop_iteration[0] += 1
                    return _base_drun_result("test output", 1, "test stderr output")
                if "get_next_pr.py" in cmd_str:
                    return _base_drun_result("[QUEUE_EMPTY]\n", 0)
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun
        mock_dpopen.return_value.returncode = 0
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)
        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir",
                    mock_workdir,
                    "--prd-file",
                    "dummy_prd.md",
                    "--force-replan",
                    "false",
                    "--channel",
                    "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir",
                    mock_workdir,
                    "--max-prs-to-process",
                    "1",
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        preflight_calls = [
            c for c in mock_notify.call_args_list if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) > 0

        matching_limit_calls = [
            c for c in preflight_calls if c[0][3]["attempt"] == c[0][3]["limit"]
        ]
        assert matching_limit_calls

        assert mock_teardown.call_count > 0 or loop_iteration[0] >= 3
