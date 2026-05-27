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

NULL_OUTPUT_SYSTEM_ALERT = """SYSTEM ALERT: Your previous coder round produced no implementation artifacts.

Detected state:
- no file delta
- no commit delta

This means your previous round is INVALID for SDLC automation.
Acknowledgment-only completion (for example “I’ve read the task”, “I’m ready”, or similar readiness/status-only replies) does NOT count as progress.

You must continue autonomously from the current branch state and produce real implementation artifacts that satisfy the PR contract:
- create/modify the required files
- run the relevant tests and ./preflight.sh if required
- commit the changed files
- leave git status clean
- report the new HEAD commit hash

Forbidden outcomes:
- “I’m ready for the next step”
- “I understand the task”
- any status-only or acknowledgment-only response without implementation artifacts

A narrative explanation without code, tests, and commit does not count as successful completion.
If you again produce no implementation artifacts, the orchestrator will escalate through the existing recovery path."""


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


def test_null_output_routes_back_to_coder_system_alert_before_reviewer(mock_workdir_with_preflight):
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

        call_state = {"status_calls": 0, "preflight_calls": 0, "next_calls": 0}

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    call_state["status_calls"] += 1
                    return _mock_result("")
                if "branch --show-current" in cmd_str:
                    return _mock_result("master\n")
                if cmd[:3] == ["git", "show-ref", "--verify"]:
                    return _mock_result("", 0)
                if "preflight.sh" in cmd_str:
                    call_state["preflight_calls"] += 1
                    return _mock_result("ok", 0)
                if "get_next_pr.py" in cmd_str:
                    call_state["next_calls"] += 1
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

        dpopen_calls = mock_dpopen.call_args_list
        coder_calls = [c for c in dpopen_calls if "spawn_coder.py" in " ".join(c[0][0])]
        reviewer_calls = [c for c in dpopen_calls if "spawn_reviewer.py" in " ".join(c[0][0])]

        assert len(coder_calls) >= 2
        assert "--system-alert" not in coder_calls[0][0][0]
        assert "--system-alert" in coder_calls[1][0][0]
        alert_index = coder_calls[1][0][0].index("--system-alert") + 1
        assert coder_calls[1][0][0][alert_index] == NULL_OUTPUT_SYSTEM_ALERT
        assert len(reviewer_calls) == 1
        assert any(call[0][2] == "reviewer_spawned" for call in mock_notify.call_args_list)


def test_repeated_null_output_exhausts_yellow_budget_and_enters_existing_red_path(mock_workdir_with_preflight):
    mock_workdir = mock_workdir_with_preflight
    job_dir, _pr_file = _prepare_job_dir(mock_workdir)
    config_dir = os.path.join(mock_workdir, "config")
    os.makedirs(config_dir, exist_ok=True)
    Path(os.path.join(config_dir, "sdlc_config.json")).write_text(
        '{"YELLOW_RETRY_LIMIT": 2, "RED_RETRY_LIMIT": 1}', encoding="utf-8"
    )

    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.parse_affected_projects", return_value=[]), \
         patch("orchestrator.safe_git_checkout"), \
         patch("orchestrator.set_pr_status"), \
         patch("orchestrator.get_pr_slice_depth", return_value=2), \
         patch("orchestrator.teardown_coder_session") as mock_teardown, \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.glob.glob") as mock_glob, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("orchestrator.drun") as mock_drun, \
         patch("orchestrator.get_mainline_branch", return_value="master"), \
         patch("orchestrator.get_head_commit_hash", side_effect=["abc123", "abc123", "abc123", "abc123"]), \
         patch("agent_driver.send_ignition_handshake"):

        mock_dpopen.side_effect = [DummyProc(0), DummyProc(0)]
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch --show-current" in cmd_str:
                    return _mock_result("master\n")
                if cmd[:3] == ["git", "show-ref", "--verify"]:
                    return _mock_result("", 0)
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    return _mock_result("")
                if cmd[:3] == ["git", "reset", "--hard"]:
                    raise SystemExit(1)
                if "get_next_pr.py" in cmd_str:
                    return _mock_result("[QUEUE_EMPTY]\n", 0)
                if cmd[:3] == ["git", "clean", "-fd"] or cmd[:3] == ["git", "branch", "-D"] or cmd[:2] == ["git", "checkout"]:
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

        dpopen_calls = mock_dpopen.call_args_list
        coder_calls = [c for c in dpopen_calls if "spawn_coder.py" in " ".join(c[0][0])]
        reviewer_calls = [c for c in dpopen_calls if "spawn_reviewer.py" in " ".join(c[0][0])]

        assert len(coder_calls) == 2
        assert "--system-alert" not in coder_calls[0][0][0]
        assert "--system-alert" in coder_calls[1][0][0]
        assert len(reviewer_calls) == 0
        assert mock_teardown.call_count > 0
        assert not any(call[0][2] == "reviewer_spawned" for call in mock_notify.call_args_list)


def test_real_coder_commit_still_advances_to_reviewer(mock_workdir_with_preflight):
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
         patch("orchestrator.get_head_commit_hash", side_effect=["abc123", "def456"]), \
         patch("agent_driver.send_ignition_handshake"):

        mock_dpopen.side_effect = [DummyProc(0), DummyProc(0)]
        mock_glob.side_effect = seeded_job_dir_glob_side_effect(job_dir)

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch --show-current" in cmd_str:
                    return _mock_result("master\n")
                if cmd[:3] == ["git", "show-ref", "--verify"]:
                    return _mock_result("", 0)
                if cmd[:3] == ["git", "status", "--porcelain"]:
                    return _mock_result("")
                if "preflight.sh" in cmd_str:
                    return _mock_result("ok", 0)
                if "get_next_pr.py" in cmd_str:
                    return _mock_result("[QUEUE_EMPTY]\n", 0)
                if cmd[:3] == ["git", "reset", "--hard"] or cmd[:3] == ["git", "clean", "-fd"]:
                    return _mock_result("", 0)
                if "merge_code.py" in cmd_str or cmd[:2] == ["git", "checkout"] or cmd[:3] == ["git", "branch", "-D"]:
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

        dpopen_calls = mock_dpopen.call_args_list
        coder_calls = [c for c in dpopen_calls if "spawn_coder.py" in " ".join(c[0][0])]
        reviewer_calls = [c for c in dpopen_calls if "spawn_reviewer.py" in " ".join(c[0][0])]

        assert len(coder_calls) == 1
        assert "--system-alert" not in coder_calls[0][0][0]
        assert len(reviewer_calls) == 1
        assert any(call[0][2] == "reviewer_spawned" for call in mock_notify.call_args_list)


def test_stateless_coder_retry_uses_previous_output_flag():
    """TC4: When continuity_mode=stateless and feedback file present, the
    orchestrator passes --previous-output pointing to the .tmp stdout file."""
    import tempfile

    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = tmp_dir
        global_dir = tmp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir, global_dir, prd_filename="dummy.md", pr_slice_content="status: in_progress\n"
        )

        with patch("orchestrator.subprocess.Popen") as mock_popen, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.safe_git_checkout"), \
             patch("orchestrator.glob.glob") as mock_glob, \
             patch("orchestrator.set_pr_status"), \
             patch("git_utils.check_git_boundary"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(seeded["job_dir"])
            mock_run.return_value = MagicMock(returncode=0, stdout="deadbeef\n", stderr="")
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.wait.return_value = 0
            mock_popen.return_value.poll.return_value = 0

            with patch("orchestrator.load_engine_registry", return_value={
                "engines": {
                    "openclaw_native": {
                        "engine_id": "openclaw_native",
                        "cli_alias": "openclaw",
                        "continuity_mode": "stateless",
                    }
                }
            }):
                with patch(
                    "sys.argv",
                    [
                        "orchestrator.py",
                        "--workdir", workdir,
                        "--prd-file", "dummy.md",
                        "--force-replan", "false",
                        "--channel", "test",
                        "--enable-exec-from-workspace",
                        "--global-dir", global_dir,
                        "--max-prs-to-process", "1",
                    ],
                ):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # Verify --previous-output points into .tmp when present
            for call_args in mock_popen.call_args_list:
                cmd = list(call_args[0][0]) if call_args[0] else []
                for i, arg in enumerate(cmd):
                    if str(arg) == "--previous-output" and i + 1 < len(cmd):
                        stdout_path = str(cmd[i + 1])
                        assert ".tmp" in stdout_path, f"stdout not in .tmp: {stdout_path}"
                        assert ".coder_stdout_" in stdout_path
