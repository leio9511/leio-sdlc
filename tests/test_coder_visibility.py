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
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, ".git"), exist_ok=True)
        Path(os.path.join(temp_dir, "preflight.sh")).write_text(
            "#!/bin/bash\necho preflight\n", encoding="utf-8"
        )
        yield temp_dir


class DummyProc:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.pid = 12345

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode


def _mock_result(stdout="", returncode=0, stderr=""):
    res = MagicMock()
    res.stdout = stdout
    res.stderr = stderr
    res.returncode = returncode
    return res


def _prepare_job_dir(workdir):
    seeded = seed_planner_success_artifacts(
        workdir,
        workdir,
        prd_filename="dummy_prd.md",
        pr_slice_content="status: in_progress\n",
    )
    return seeded["job_dir"], seeded["pr_file"]


def test_coder_no_output_notification(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_job_dir(mock_workdir)

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.teardown_coder_session"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.extract_and_parse_json", return_value={"overall_assessment": "EXCELLENT"}), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.get_mainline_branch", return_value="master"), \
         patch("orchestrator.get_head_commit_hash", side_effect=["abc123", "abc123", "abc123", "def456"]), \
         patch("agent_driver.send_ignition_handshake"):

        mock_dpopen.side_effect = [DummyProc(0), DummyProc(0), DummyProc(0)]
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    return _mock_result("")
                if "branch --show-current" in cmd_str:
                    return _mock_result("master\n")
                if cmd[:3] == ["git", "show-ref", "--verify"]:
                    return _mock_result("", 0)
                if "preflight.sh" in cmd_str:
                    return _mock_result("ok", 0)
                if "get_next_pr.py" in cmd_str:
                    return _mock_result("[QUEUE_EMPTY]\n", 0)
                if cmd[:3] == ["git", "reset", "--hard"] or cmd[:3] == ["git", "clean", "-fd"] or cmd[:3] == ["git", "branch", "-D"]:
                    return _mock_result("", 0)
            return _mock_result("", 0)

        mock_drun.side_effect = dummy_drun

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

        # Verify notify_channel was called with coder_no_output
        called_with_no_output = any(
            call.args[2] == "coder_no_output" for call in mock_notify.call_args_list if len(call.args) > 2
        )
        assert called_with_no_output, "Orchestrator did not send coder_no_output notification."


def test_coder_dirty_workspace_notification(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_job_dir(mock_workdir)

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.teardown_coder_session"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.extract_and_parse_json", return_value={"overall_assessment": "EXCELLENT"}), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.get_mainline_branch", return_value="master"), \
         patch("orchestrator.get_head_commit_hash", side_effect=["abc123", "def456", "def456", "ghi789"]), \
         patch("agent_driver.send_ignition_handshake"):

        mock_dpopen.side_effect = [DummyProc(0), DummyProc(0), DummyProc(0)]
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)

        status_calls = 0
        def dummy_drun(cmd, *args, **kwargs):
            nonlocal status_calls
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    status_calls += 1
                    if status_calls == 2:  # First check in main, second is coder check
                        return _mock_result(" M some_file.py\n")
                    return _mock_result("")
                if "branch --show-current" in cmd_str:
                    return _mock_result("master\n")
                if cmd[:3] == ["git", "show-ref", "--verify"]:
                    return _mock_result("", 0)
                if "preflight.sh" in cmd_str:
                    return _mock_result("ok", 0)
                if "get_next_pr.py" in cmd_str:
                    return _mock_result("[QUEUE_EMPTY]\n", 0)
                if cmd[:3] == ["git", "reset", "--hard"] or cmd[:3] == ["git", "clean", "-fd"] or cmd[:3] == ["git", "branch", "-D"]:
                    return _mock_result("", 0)
            return _mock_result("", 0)

        mock_drun.side_effect = dummy_drun

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

        # Verify notify_channel was called with coder_workspace_dirty
        called_with_workspace_dirty = any(
            call.args[2] == "coder_workspace_dirty" for call in mock_notify.call_args_list if len(call.args) > 2
        )
        assert called_with_workspace_dirty, "Orchestrator did not send coder_workspace_dirty notification."
