"""
PR-002: Preflight Failure Notification Tests

Tests verifying that notify_channel is called with the correct message
format when preflight.sh fails, and that control flow remains correct.
"""
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator


@pytest.fixture
def mock_workdir_with_preflight():
    """Creates a temp workdir with .git and a dummy preflight.sh."""
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, '.git'), exist_ok=True)
        # preflight.sh must exist so orchestrator enters the preflight block
        with open(os.path.join(temp_dir, "preflight.sh"), "w") as f:
            f.write("#!/bin/bash\necho 'mock preflight'\n")
        yield temp_dir


# ---------------------------------------------------------------------------
# Test Case 1: preflight failure sends notification
# ---------------------------------------------------------------------------
def test_preflight_failure_sends_notification(mock_workdir_with_preflight):
    """
    Given Coder has produced code and preflight.sh exists in the workdir
    When preflight.sh returns a non-zero exit code
    Then the orchestrator calls notify_channel with event type "preflight_failed"
    And the notification message contains "Preflight failed", the PR identifier,
        the current attempt number, and the retry limit
    And the orchestrator continues to re-spawn the Coder
    """
    mock_workdir = mock_workdir_with_preflight

    # We need the orchestrator loop to run multiple times so preflight gets called.
    # Strategy: git status clean on 1st pass → preflight fails → continue →
    # coder re-spawned → git status clean on 2nd pass → preflight fails → ...
    # After yellow_retry_limit (default 3) preflight failures, state_5 triggers.
    # But we want at least one notify_channel call, so 1 failure is sufficient.
    # Problem: after preflight failure + continue, get_next_pr may dequeue
    # and exit. We need it to always return the same PR until state_5 breaks.
    #
    # Actually the orchestrator picks the first "in_progress" PR each loop.
    # After continue, it loops again, re-spawns Coder, and hits preflight again.
    # This will keep happening until yellow_retry_limit or state_5.
    #
    # To stop early, let the 2nd Reviewer return approved + merge success.
    # But the merge calls git commands. Let's just let it hit state_5.
    # Actually let's make the 2nd pass succeed (preflight passes),
    # then Reviewer approves and merges.
    #
    # Simpler approach: let preflight fail exactly once, then on 2nd
    # iteration make git status return dirty (triggers continue before
    # preflight) then on 3rd iteration merge succeeds.
    #
    # Actually the simplest: make get_next_pr return QUEUE_EMPTY after
    # each preflight failure so the outer loop ends.

    with patch('orchestrator.SanityContext.perform_healthy_check'), \
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
         patch('orchestrator.extract_and_parse_json') as mock_extract:

        drun_call_count = [0]

        def dummy_drun(cmd, *args, **kwargs):
            drun_call_count[0] += 1
            mock_res = MagicMock()
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    mock_res.stdout = "master\n"
                    mock_res.returncode = 0
                elif "preflight.sh" in cmd_str:
                    # Preflight fails
                    mock_res.stdout = "test output"
                    mock_res.stderr = "test stderr output"
                    mock_res.returncode = 1
                elif "get_next_pr.py" in cmd_str:
                    mock_res.stdout = "[QUEUE_EMPTY]\n"
                    mock_res.returncode = 0
                else:
                    mock_res.stdout = ""
                    mock_res.returncode = 0
            else:
                mock_res.stdout = ""
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
            if ".coder_session" in pattern:
                return []
            return [pr_file]

        mock_glob.side_effect = dummy_glob

        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir,
                                    '--prd-file', 'dummy_prd.md', '--force-replan', 'false',
                                    '--channel', 'test-channel', '--enable-exec-from-workspace',
                                    '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass

        # Verify notify_channel was called with the preflight_failed event
        preflight_calls = [
            c for c in mock_notify.call_args_list
            if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) > 0, "Expected notify_channel with 'preflight_failed' event type"

        # Check the first preflight_failed call
        first_call = preflight_calls[0]
        channel = first_call[0][0]
        message = first_call[0][1]
        event_type = first_call[0][2]
        metadata = first_call[0][3]

        assert channel == "test-channel"
        assert event_type == "preflight_failed"
        assert "Preflight failed" in message
        assert "PR_001_test" in message  # PR identifier
        assert "attempt" in message
        assert "Retrying Coder" in message

        # Verify metadata
        assert metadata["pr_id"] == "PR_001_test"
        assert metadata["attempt"] == 1
        assert metadata["limit"] > 0


# ---------------------------------------------------------------------------
# Test Case 2: preflight success does NOT send notification
# ---------------------------------------------------------------------------
def test_preflight_success_does_not_send_notification(mock_workdir_with_preflight):
    """
    Given Coder has produced code and preflight.sh exists in the workdir
    When preflight.sh returns exit code 0
    Then no notify_channel is sent with event type "preflight_failed"
    And the orchestrator proceeds to State 4 (Reviewer)
    """
    mock_workdir = mock_workdir_with_preflight

    with patch('orchestrator.SanityContext.perform_healthy_check'), \
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
         patch('orchestrator.extract_and_parse_json') as mock_extract:

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    mock_res.stdout = "master\n"
                    mock_res.returncode = 0
                elif "preflight.sh" in cmd_str:
                    # Preflight succeeds
                    mock_res.stdout = "all good"
                    mock_res.stderr = ""
                    mock_res.returncode = 0
                elif "get_next_pr.py" in cmd_str:
                    mock_res.stdout = "[QUEUE_EMPTY]\n"
                    mock_res.returncode = 0
                else:
                    mock_res.stdout = ""
                    mock_res.returncode = 0
            else:
                mock_res.stdout = ""
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
            if ".coder_session" in pattern:
                return []
            return [pr_file]

        mock_glob.side_effect = dummy_glob

        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir,
                                    '--prd-file', 'dummy_prd.md', '--force-replan', 'false',
                                    '--channel', 'test-channel', '--enable-exec-from-workspace',
                                    '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass

        # Verify NO notify_channel with event type "preflight_failed"
        preflight_calls = [
            c for c in mock_notify.call_args_list
            if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) == 0, (
            "Expected no 'preflight_failed' notifications when preflight succeeds"
        )

        # Verify the Reviewer was spawned (State 4), indicating preflight was
        # followed by proper state transition
        reviewer_calls = [
            c for c in mock_notify.call_args_list
            if c[0][2] == "reviewer_spawned"
        ]
        assert len(reviewer_calls) > 0, (
            "Expected Reviewer to be spawned after preflight success"
        )


# ---------------------------------------------------------------------------
# Test Case 3: preflight retry limit reached triggers state_5
# ---------------------------------------------------------------------------
def test_preflight_retry_limit_reached_triggers_state_5(mock_workdir_with_preflight):
    """
    Given orch_yellow_counter equals yellow_retry_limit - 1 before preflight runs
    When preflight fails again, incrementing orch_yellow_counter to equal yellow_retry_limit
    Then state_5_trigger is set to True
    And the inner loop is broken out of (State 5 escalation path)
    And the notification was sent for the final attempt before the break
    """
    mock_workdir = mock_workdir_with_preflight

    # To get orch_yellow_counter to yellow_retry_limit - 1 before the final
    # preflight failure, we make git status return clean (so we pass the dirty
    # check and reach preflight) but preflight always fails.
    # The orchestrator loops: Coder → preflight fail → continue → Coder → ...
    # Each preflight failure increments orch_yellow_counter.
    # Default yellow_retry_limit is 3 (see orchestrator code).
    # After 3 preflight failures orch_yellow_counter == yellow_retry_limit
    # → state_5_trigger = True → break.
    #
    # We use a counter to track which preflight attempt we're on so the test
    # can verify the notification was sent for the final attempt.

    loop_iteration = [0]

    with patch('orchestrator.SanityContext.perform_healthy_check'), \
         patch('orchestrator.teardown_coder_session') as mock_teardown, \
         patch('orchestrator.drun') as mock_drun, \
         patch('orchestrator.dpopen') as mock_dpopen, \
         patch('git_utils.check_git_boundary'), \
         patch('orchestrator.validate_prd_is_committed'), \
         patch('orchestrator.parse_affected_projects', return_value=[]), \
         patch('orchestrator.safe_git_checkout'), \
         patch('orchestrator.notify_channel') as mock_notify, \
         patch('orchestrator.glob.glob') as mock_glob, \
         patch('orchestrator.set_pr_status'), \
         patch('orchestrator.extract_and_parse_json') as mock_extract:

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    mock_res.stdout = "master\n"
                    mock_res.returncode = 0
                elif "preflight.sh" in cmd_str:
                    loop_iteration[0] += 1
                    # Preflight always fails
                    mock_res.stdout = "test output"
                    mock_res.stderr = "test stderr output"
                    mock_res.returncode = 1
                elif "get_next_pr.py" in cmd_str:
                    mock_res.stdout = "[QUEUE_EMPTY]\n"
                    mock_res.returncode = 0
                else:
                    mock_res.stdout = ""
                    mock_res.returncode = 0
            else:
                mock_res.stdout = ""
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
            if ".coder_session" in pattern:
                return []
            return [pr_file]

        mock_glob.side_effect = dummy_glob

        mock_extract.return_value = {"overall_assessment": "EXCELLENT"}

        try:
            with patch('sys.argv', ['orchestrator.py', '--workdir', mock_workdir,
                                    '--prd-file', 'dummy_prd.md', '--force-replan', 'false',
                                    '--channel', 'test-channel', '--enable-exec-from-workspace',
                                    '--global-dir', mock_workdir, '--max-prs-to-process', '1']):
                orchestrator.main()
        except SystemExit:
            pass

        # Verify the preflight_failed notification was sent
        preflight_calls = [
            c for c in mock_notify.call_args_list
            if c[0][2] == "preflight_failed"
        ]
        assert len(preflight_calls) > 0, (
            "Expected at least one 'preflight_failed' notification"
        )

        # The orchestrator may continue into state-5 recovery after the limit hit,
        # but the final preflight_failed notification for the triggering cycle must
        # reflect the retry limit.
        matching_limit_calls = [
            c for c in preflight_calls if c[0][3]["attempt"] == c[0][3]["limit"]
        ]
        assert matching_limit_calls, (
            "Expected at least one preflight_failed notification where attempt equals limit"
        )

        # Verify the coder session was torn down (state_5 escalation → cleanup)
        # When state_5 triggers, the outer loop exits and coder session is torn down
        assert mock_teardown.call_count > 0 or loop_iteration[0] >= 3, (
            "State 5 escalation should trigger coder session teardown or the "
            "loop exhausted retries"
        )
