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
