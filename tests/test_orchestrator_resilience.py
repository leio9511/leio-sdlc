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
def mock_workdir():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, ".git"))
        yield temp_dir


def test_blast_radius_clears_sessions(mock_workdir):
    session1 = os.path.join(mock_workdir, ".coder_session")
    session2 = os.path.join(mock_workdir, "sub", ".coder_session")
    os.makedirs(os.path.dirname(session2), exist_ok=True)

    with open(session1, "w") as f:
        f.write("test_session_1")
    with open(session2, "w") as f:
        f.write("test_session_2")

    assert os.path.exists(session1)
    assert os.path.exists(session2)

    with patch("orchestrator.drun") as mock_drun, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("agent_driver.send_ignition_handshake"), \
         patch(
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
                 "--test-sleep",
                 "--enable-exec-from-workspace",
                 "--global-dir",
                 mock_workdir,
             ],
         ):

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = "master\n" if isinstance(cmd, list) and "branch" in cmd else ""
            mock_res.returncode = 0
            return mock_res

        mock_drun.side_effect = dummy_drun

        try:
            with patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
                orchestrator.main()
        except SystemExit as e:
            assert e.code == 0

    assert not os.path.exists(session1)
    assert not os.path.exists(session2)


def test_yellow_path_preserves_session(mock_workdir):
    seeded = seed_planner_success_artifacts(
        mock_workdir,
        mock_workdir,
        prd_filename="dummy_prd.md",
        pr_slice_content="status: in_progress\n",
    )

    with patch("orchestrator.teardown_coder_session") as mock_teardown, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch(
             "orchestrator.extract_and_parse_json",
             side_effect=[
                 {"overall_assessment": "NEEDS_ATTENTION"},
                 {"overall_assessment": "EXCELLENT"},
             ],
         ), \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.notify_channel"), \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.set_pr_status"), \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = ""
            mock_res.returncode = 0
            if isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            return mock_res

        mock_drun.side_effect = dummy_drun
        mock_dpopen.return_value.returncode = 0
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(seeded["job_dir"])

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
                with patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
                    orchestrator.main()
        except SystemExit:
            pass

        assert mock_teardown.call_count == 1


def test_red_path_hard_resets(mock_workdir):
    seeded = seed_planner_success_artifacts(
        mock_workdir,
        mock_workdir,
        prd_filename="dummy_prd.md",
        pr_slice_content="status: in_progress\n",
    )
    glob_counts = {"job_dir_scans": 0}

    with patch("orchestrator.teardown_coder_session") as mock_teardown, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch(
             "orchestrator.extract_and_parse_json",
             side_effect=[
                 {"overall_assessment": "NEEDS_ATTENTION"},
                 {"overall_assessment": "NEEDS_ATTENTION"},
                 {"overall_assessment": "NEEDS_ATTENTION"},
                 {"overall_assessment": "NEEDS_ATTENTION"},
                 {"overall_assessment": "EXCELLENT"},
             ],
         ), \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.notify_channel"), \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.get_pr_slice_depth", return_value=0), \
         patch("orchestrator.set_pr_status"), \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.stdout = ""
            mock_res.returncode = 0
            if isinstance(cmd, list) and "branch" in cmd:
                mock_res.stdout = "master\n"
            return mock_res

        def dummy_glob(pattern, recursive=False):
            if ".coder_session" in pattern:
                return []
            if pattern == os.path.join(seeded["job_dir"], "*.md"):
                glob_counts["job_dir_scans"] += 1
                if glob_counts["job_dir_scans"] > 5:
                    return []
            return seeded_job_dir_glob_side_effect(seeded["job_dir"])(pattern, recursive)

        mock_drun.side_effect = dummy_drun
        mock_glob.side_effect = dummy_glob
        mock_dpopen.return_value.communicate.return_value = ("REJECTED", "")
        mock_dpopen.return_value.returncode = 1

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
                with patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
                    orchestrator.main()
        except SystemExit:
            pass

        assert mock_teardown.call_count > 0


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_stateless_reviewer_json_parse_retry_uses_full_reprompt(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC1: When a stateless reviewer returns non-JSON, the retry is a fresh
    full reviewer invocation containing PRD, PR contract, diff target/evidence,
    and retry alert — not a --system-alert call."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = tmp_dir
        global_dir = tmp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir,
            global_dir,
            prd_filename="dummy.md",
            pr_slice_content="status: in_progress\n",
        )

        with patch("orchestrator.teardown_coder_session") as mock_teardown, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.subprocess.Popen") as mock_popen, \
             patch("orchestrator.safe_git_checkout"), \
             patch("orchestrator.glob.glob") as mock_glob, \
             patch("orchestrator.set_pr_status"), \
             patch("git_utils.check_git_boundary"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("orchestrator.classify_coder_null_output", return_value=(False, "", "different_hash")), \
             patch.object(
                 orchestrator.SanityContext, "perform_healthy_check", return_value=None
             ):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(
                seeded["job_dir"]
            )

            def dummy_run_tc1(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = ""
                res.stderr = ""
                res.returncode = 0
                if isinstance(cmd, list):
                    cmd_str = " ".join(cmd)
                    if "branch" in cmd_str:
                        res.stdout = "master\n"
                    if "status --porcelain" in cmd_str:
                        res.stdout = ""
                    if "rev-parse" in cmd_str:
                        res.stdout = "deadbeef\n"
                return res

            mock_run.side_effect = dummy_run_tc1
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.wait.return_value = 0
            mock_popen.return_value.returncode = 0
            mock_popen.return_value.poll.return_value = 0

            # Use a stateless engine
            with patch(
                "orchestrator.load_engine_registry",
                return_value={
                    "engines": {
                        "gemini_direct_cli": {
                            "engine_id": "gemini_direct_cli",
                            "cli_alias": "gemini",
                            "continuity_mode": "stateless",
                        }
                    }
                },
            ):
                with patch(
                    "sys.argv",
                    [
                        "orchestrator.py",
                        "--force-replan",
                        "false",
                        "--enable-exec-from-workspace",
                        "--workdir",
                        workdir,
                        "--prd-file",
                        "dummy.md",
                        "--channel",
                        "test",
                        "--global-dir",
                        global_dir,
                        "--coder-session-strategy",
                        "always",
                        "--max-prs-to-process",
                        "1",
                        "--engine",
                        "gemini",
                    ],
                ):
                    # Simulate extract_and_parse_json: first call raises ValueError (non-JSON),
                    # second call succeeds with EXCELLENT
                    with patch(
                        "orchestrator.extract_and_parse_json",
                        side_effect=[
                            ValueError("Bad JSON"),
                            {"overall_assessment": "EXCELLENT"},
                        ],
                    ):
                        try:
                            orchestrator.main()
                        except SystemExit:
                            pass

            # Verify the retry was a full invocation with --inline-alert, NOT --system-alert
            dpopen_calls = mock_popen.call_args_list
            reviewer_calls = [
                call
                for call in dpopen_calls
                if "spawn_reviewer.py"
                in " ".join(call[0][0]) if isinstance(call[0][0], list)
            ]

            # Should have at least two reviewer calls (initial + retry)
            assert len(reviewer_calls) >= 2, (
                f"Expected at least 2 reviewer calls, got {len(reviewer_calls)}"
            )

            # The retry (second call) should use --inline-alert, not --system-alert
            system_alert_calls = [
                call
                for call in reviewer_calls
                if "--system-alert" in call[0][0]
            ]
            inline_alert_calls = [
                call
                for call in reviewer_calls
                if "--inline-alert" in call[0][0]
            ]
            assert len(system_alert_calls) == 0, (
                "No --system-alert calls expected for stateless engine"
            )
            assert len(inline_alert_calls) >= 1, (
                f"Expected at least 1 --inline-alert call, got {len(inline_alert_calls)}"
            )

            # Verify the full invocation args are present
            retry_cmd = inline_alert_calls[0][0][0]
            retry_cmd_str = " ".join(retry_cmd)
            assert "--prd-file" in retry_cmd_str
            assert "--pr-file" in retry_cmd_str
            assert "--diff-target" in retry_cmd_str
            assert "--workdir" in retry_cmd_str


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_reviewer_retry_alert_contains_previous_output_and_schema(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC2: The retry alert includes the exact REVIEWER_RETRY_ALERT text,
    previous raw output, and required schema."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = tmp_dir
        global_dir = tmp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir,
            global_dir,
            prd_filename="dummy.md",
            pr_slice_content="status: in_progress\n",
        )

        with patch("orchestrator.teardown_coder_session") as mock_teardown, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.subprocess.Popen") as mock_popen, \
             patch("orchestrator.safe_git_checkout"), \
             patch("orchestrator.glob.glob") as mock_glob, \
             patch("orchestrator.set_pr_status"), \
             patch("git_utils.check_git_boundary"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("orchestrator.classify_coder_null_output", return_value=(False, "", "different_hash")), \
             patch.object(
                 orchestrator.SanityContext, "perform_healthy_check", return_value=None
             ):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(
                seeded["job_dir"]
            )

            def dummy_run_tc2(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = ""
                res.stderr = ""
                res.returncode = 0
                if isinstance(cmd, list):
                    cmd_str = " ".join(cmd)
                    if "branch" in cmd_str:
                        res.stdout = "master\n"
                    if "status --porcelain" in cmd_str:
                        res.stdout = ""
                    if "rev-parse" in cmd_str:
                        res.stdout = "deadbeef\n"
                return res

            mock_run.side_effect = dummy_run_tc2
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.wait.return_value = 0
            mock_popen.return_value.returncode = 0
            mock_popen.return_value.poll.return_value = 0

            with patch(
                "orchestrator.load_engine_registry",
                return_value={
                    "engines": {
                        "gemini_direct_cli": {
                            "engine_id": "gemini_direct_cli",
                            "cli_alias": "gemini",
                            "continuity_mode": "stateless",
                        }
                    }
                },
            ):
                with patch(
                    "sys.argv",
                    [
                        "orchestrator.py",
                        "--force-replan",
                        "false",
                        "--enable-exec-from-workspace",
                        "--workdir",
                        workdir,
                        "--prd-file",
                        "dummy.md",
                        "--channel",
                        "test",
                        "--global-dir",
                        global_dir,
                        "--coder-session-strategy",
                        "always",
                        "--max-prs-to-process",
                        "1",
                        "--engine",
                        "gemini",
                    ],
                ):
                    with patch(
                        "orchestrator.extract_and_parse_json",
                        side_effect=[
                            ValueError("Bad JSON"),
                            {"overall_assessment": "EXCELLENT"},
                        ],
                    ):
                        try:
                            orchestrator.main()
                        except SystemExit:
                            pass

            # Find the --inline-alert argument value
            dpopen_calls = mock_popen.call_args_list
            inline_alert_calls = [
                call
                for call in dpopen_calls
                if "spawn_reviewer.py" in " ".join(call[0][0])
                and "--inline-alert" in call[0][0]
            ]
            assert len(inline_alert_calls) >= 1

            retry_cmd = inline_alert_calls[0][0][0]
            # Find the index of --inline-alert and get its value
            alert_idx = retry_cmd.index("--inline-alert")
            alert_value = retry_cmd[alert_idx + 1]

            assert "SYSTEM ALERT" in alert_value
            assert "previous output could not be parsed as valid JSON" in alert_value
            assert "## PREVIOUS OUTPUT (NON-JSON)" in alert_value
            assert "## REQUIRED SCHEMA" in alert_value
            assert "overall_assessment" in alert_value
            assert "findings" in alert_value


def test_classify_coder_null_output_signature():
    import inspect
    from orchestrator import classify_coder_null_output
    sig = inspect.signature(classify_coder_null_output)
    params = list(sig.parameters.values())
    assert len(params) == 4
    assert params[3].name == "default_branch"
    assert params[3].default is None

