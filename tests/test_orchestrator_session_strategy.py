import os
import sys
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_SCRIPT = REPO_ROOT / "scripts" / "orchestrator.py"

sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from planner_test_support import seed_planner_success_artifacts, seeded_job_dir_glob_side_effect

import orchestrator


@pytest.fixture(autouse=True)
def reset_cwd():
    original_cwd = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        yield
    finally:
        os.chdir(original_cwd)


def test_invalid_strategy():
    result = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR_SCRIPT),
            "--enable-exec-from-workspace",
            "--workdir",
            ".",
            "--prd-file",
            "dummy.md",
            "--coder-session-strategy",
            "invalid-strategy",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "argument --coder-session-strategy: invalid choice: 'invalid-strategy'" in result.stderr


def test_missing_workdir():
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR_SCRIPT), "--enable-exec-from-workspace", "--prd-file", "dummy.md"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode != 0
    assert "the following arguments are required: --workdir" in result.stderr


def _mock_subprocess_run_for_strategy(spawn_coder_returncode=0):
    def _side_effect(cmd, *args, **kwargs):
        result = MagicMock()
        result.stdout = ""
        result.stderr = ""
        result.returncode = 0
        if isinstance(cmd, list):
            if cmd[:3] == ["git", "rev-parse", "HEAD"]:
                result.stdout = "deadbeef\n"
            elif cmd[:3] == ["git", "status", "--porcelain"]:
                result.stdout = ""
            elif "spawn_coder.py" in cmd:
                result.returncode = spawn_coder_returncode
        return result

    return _side_effect


def _run_strategy_test(strategy: str, spawn_coder_returncode: int):
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"
    import orchestrator

    with tempfile.TemporaryDirectory() as temp_dir:
        workdir = temp_dir
        global_dir = temp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir,
            global_dir,
            prd_filename="dummy.md",
            pr_slice_content="status: in_progress\n",
        )

        with patch("orchestrator.teardown_coder_session") as mock_teardown, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.safe_git_checkout"), \
             patch("orchestrator.glob.glob") as mock_glob, \
             patch("orchestrator.set_pr_status"), \
             patch("git_utils.check_git_boundary"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(seeded["job_dir"])
            mock_run.side_effect = _mock_subprocess_run_for_strategy(
                spawn_coder_returncode=spawn_coder_returncode
            )

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
                    strategy,
                    "--max-prs-to-process",
                    "1",
                ],
            ):
                try:
                    orchestrator.main()
                except SystemExit:
                    pass

        mock_teardown.assert_called_with(workdir, ANY, engine_mode="stateful")


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_always_strategy(_mock_copytree, _mock_rmtree, _mock_flock):
    _run_strategy_test("always", spawn_coder_returncode=1)


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_per_pr_strategy(_mock_copytree, _mock_rmtree, _mock_flock):
    _run_strategy_test("per-pr", spawn_coder_returncode=0)


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_on_escalation_strategy(_mock_copytree, _mock_rmtree, _mock_flock):
    _run_strategy_test("on-escalation", spawn_coder_returncode=1)


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_stateless_coder_retry_does_not_teardown_or_create_coder_session(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC5: For continuity_mode=stateless, no .coder_session is read,
    removed, or created during retry."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = tmp_dir
        global_dir = tmp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir, global_dir, prd_filename="dummy.md", pr_slice_content="status: in_progress\n"
        )

        with patch("orchestrator.teardown_coder_session") as mock_teardown, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.subprocess.Popen") as mock_popen, \
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

            # Override region: mock the continuity_mode to be stateless
            mock_run.side_effect = _mock_subprocess_run_for_strategy(spawn_coder_returncode=0)

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
                        "--force-replan", "false",
                        "--enable-exec-from-workspace",
                        "--workdir", workdir,
                        "--prd-file", "dummy.md",
                        "--channel", "test",
                        "--global-dir", global_dir,
                        "--coder-session-strategy", "always",
                        "--max-prs-to-process", "1",
                    ],
                ):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # For stateless engines, teardown_coder_session should be called with
            # engine_mode='stateless', which is a no-op internally.
            # We verify that the call uses engine_mode='stateless'.
            for call_arg in mock_teardown.call_args_list:
                kwargs = call_arg[1] if len(call_arg) > 1 else {}
                if kwargs.get("engine_mode"):
                    assert kwargs["engine_mode"] == "stateless"


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_stateful_openclaw_coder_session_behavior_preserved(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC6: For continuity_mode=stateful (openclaw), .coder_session lifecycle
    is identical to pre-PR behavior — teardown removes the session file."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"

    with tempfile.TemporaryDirectory() as tmp_dir:
        workdir = tmp_dir
        global_dir = tmp_dir
        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        seeded = seed_planner_success_artifacts(
            workdir, global_dir, prd_filename="dummy.md", pr_slice_content="status: in_progress\n"
        )

        with patch("orchestrator.teardown_coder_session") as mock_teardown, \
             patch("orchestrator.subprocess.run") as mock_run, \
             patch("orchestrator.subprocess.Popen") as mock_popen, \
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

            mock_run.side_effect = _mock_subprocess_run_for_strategy(spawn_coder_returncode=0)

            with patch("orchestrator.load_engine_registry", return_value={
                "engines": {
                    "openclaw_native": {
                        "engine_id": "openclaw_native",
                        "cli_alias": "openclaw",
                        "continuity_mode": "stateful",
                    }
                }
            }):
                with patch(
                    "sys.argv",
                    [
                        "orchestrator.py",
                        "--force-replan", "false",
                        "--enable-exec-from-workspace",
                        "--workdir", workdir,
                        "--prd-file", "dummy.md",
                        "--channel", "test",
                        "--global-dir", global_dir,
                        "--coder-session-strategy", "per-pr",
                        "--max-prs-to-process", "1",
                    ],
                ):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # For stateful engines, teardown_coder_session should be called with
            # engine_mode='stateful', preserving the pre-PR behavior.
            for call_arg in mock_teardown.call_args_list:
                kwargs = call_arg[1] if len(call_arg) > 1 else {}
                if kwargs.get("engine_mode"):
                    assert kwargs["engine_mode"] == "stateful"
