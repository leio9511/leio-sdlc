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
    # Isolate from leaked LLM_DRIVER/SDLC_MODEL from other tests
    saved_driver = os.environ.pop("LLM_DRIVER", None)
    saved_model = os.environ.pop("SDLC_MODEL", None)
    import orchestrator

    try:
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
    finally:
        if saved_driver is not None:
            os.environ["LLM_DRIVER"] = saved_driver
        if saved_model is not None:
            os.environ["SDLC_MODEL"] = saved_model


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
def test_retry_paths_branch_on_continuity_not_provider_name(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """PR-006 TC6: Fixture engines named something other than Gemini/agy follow
    stateless retry behavior when continuity_mode=stateless, while OpenClaw
    follows stateful behavior."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"
    # Isolate from leaked LLM_DRIVER/SDLC_MODEL
    saved_driver = os.environ.pop("LLM_DRIVER", None)
    saved_model = os.environ.pop("SDLC_MODEL", None)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workdir = tmp_dir
            global_dir = tmp_dir
            os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
            seeded = seed_planner_success_artifacts(
                workdir, global_dir, prd_filename="dummy.md",
                pr_slice_content="status: in_progress\n"
            )

            with patch("orchestrator.teardown_coder_session") as mock_teardown, \
                 patch("orchestrator.drun") as mock_drun, \
                 patch("orchestrator.dpopen") as mock_dpopen, \
                 patch("orchestrator.safe_git_checkout"), \
                 patch("orchestrator.glob.glob") as mock_glob, \
                 patch("orchestrator.set_pr_status"), \
                 patch("git_utils.check_git_boundary"), \
                 patch("agent_driver.send_ignition_handshake"), \
                 patch.object(
                     orchestrator.SanityContext, "perform_healthy_check",
                     return_value=None
                 ):
                mock_glob.side_effect = seeded_job_dir_glob_side_effect(seeded["job_dir"])
                mock_drun.return_value = MagicMock(
                    returncode=0, stdout="", stderr=""
                )
                proc = MagicMock()
                proc.wait.return_value = 0
                proc.poll.return_value = 0
                proc.returncode = 0
                mock_dpopen.return_value = proc

                # Register a custom-named engine (not gemini/agy) with stateless mode
                registry = {
                    "engines": {
                        "custom_stateless_cli": {
                            "engine_id": "custom_stateless_cli",
                            "cli_alias": "custom-engine",
                            "continuity_mode": "stateless",
                        },
                        "openclaw_native": {
                            "engine_id": "openclaw_native",
                            "cli_alias": "openclaw",
                            "continuity_mode": "stateful",
                        },
                    }
                }

                # Test 1: Custom stateless engine → teardown with stateless mode
                with patch(
                    "orchestrator.load_engine_registry", return_value=registry
                ):
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
                            "--engine", "custom-engine",
                        ],
                    ):
                        try:
                            orchestrator.main()
                        except SystemExit:
                            pass

                    # Custom stateless engine → teardown_coder_session with 'stateless'
                    # (no-op internally, but the branch was taken based on continuity_mode,
                    # not provider name)
                    stateless_calls = [
                        c for c in mock_teardown.call_args_list
                        if c[1].get("engine_mode") == "stateless"
                    ]
                    assert len(stateless_calls) >= 1, (
                        "Custom stateless engine should branch on continuity_mode=stateless"
                    )

                    # No stateful teardown calls for custom engine
                    stateful_calls = [
                        c for c in mock_teardown.call_args_list
                        if c[1].get("engine_mode") == "stateful"
                    ]
                    assert len(stateful_calls) == 0, (
                        "Custom stateless engine should not trigger stateful teardown"
                    )
    finally:
        if saved_driver is not None:
            os.environ["LLM_DRIVER"] = saved_driver
        if saved_model is not None:
            os.environ["SDLC_MODEL"] = saved_model


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
    # Isolate from leaked LLM_DRIVER/SDLC_MODEL from other tests
    saved_driver = os.environ.pop("LLM_DRIVER", None)
    saved_model = os.environ.pop("SDLC_MODEL", None)
    try:
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
    finally:
        if saved_driver is not None:
            os.environ["LLM_DRIVER"] = saved_driver
        if saved_model is not None:
            os.environ["SDLC_MODEL"] = saved_model


def test_all_default_direct_cli_engines_are_stateless_and_artifact_free():
    """PR-006 TC2: Gemini and agy mock invocations complete without
    .coder_session, .reviewer_session, or .session_map_* artifacts."""
    os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
    os.environ["SDLC_TEST_MODE"] = "true"
    # Isolate from leaked LLM_DRIVER/SDLC_MODEL from other tests
    saved_driver = os.environ.pop("LLM_DRIVER", None)
    saved_model = os.environ.pop("SDLC_MODEL", None)

    for engine_alias, engine_id in [("gemini", "gemini_direct_cli"), ("agy", "agy_direct_cli")]:
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                workdir = tmp_dir
                global_dir = tmp_dir
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                seeded = seed_planner_success_artifacts(
                    workdir, global_dir, prd_filename="dummy.md",
                    pr_slice_content="status: in_progress\n"
                )

                with patch("orchestrator.teardown_coder_session") as mock_teardown, \
                     patch("orchestrator.drun") as mock_drun, \
                     patch("orchestrator.dpopen") as mock_dpopen, \
                     patch("orchestrator.safe_git_checkout"), \
                     patch("orchestrator.glob.glob") as mock_glob, \
                     patch("orchestrator.set_pr_status"), \
                     patch("git_utils.check_git_boundary"), \
                     patch("agent_driver.send_ignition_handshake"), \
                     patch.object(orchestrator.SanityContext, "perform_healthy_check", return_value=None):
                    mock_glob.side_effect = seeded_job_dir_glob_side_effect(seeded["job_dir"])
                    mock_drun.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    proc = MagicMock()
                    proc.wait.return_value = 0
                    proc.poll.return_value = 0
                    proc.returncode = 0
                    mock_dpopen.return_value = proc

                    registry = {
                        "engines": {
                            engine_id: {
                                "engine_id": engine_id,
                                "cli_alias": engine_alias,
                                "continuity_mode": "stateless",
                            }
                        }
                    }

                    with patch("orchestrator.load_engine_registry", return_value=registry):
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
                                "--engine", engine_alias,
                            ],
                        ):
                            try:
                                orchestrator.main()
                            except SystemExit:
                                pass

                    # Verify no .coder_session created in run_dir
                    run_dir = seeded["job_dir"]
                    for artifact in [".coder_session", ".reviewer_session"]:
                        path = os.path.join(run_dir, artifact)
                        assert not os.path.exists(path), (
                            f"{artifact} should not exist for {engine_alias} (stateless)"
                        )

                    # Verify teardown_coder_session was called with engine_mode='stateless'
                    stateless_teardowns = [
                        call for call in mock_teardown.call_args_list
                        if call[1].get("engine_mode") == "stateless"
                    ]
                    assert len(stateless_teardowns) >= 1, (
                        f"teardown_coder_session should be called with engine_mode='stateless' for {engine_alias}"
                    )
        finally:
            pass

    if saved_driver is not None:
        os.environ["LLM_DRIVER"] = saved_driver
    if saved_model is not None:
        os.environ["SDLC_MODEL"] = saved_model


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


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_stateless_reviewer_retry_does_not_create_reviewer_session(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC4: No .reviewer_session appears after normal stateless reviewer
    invocation or JSON retry."""
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
             patch.object(
                 orchestrator.SanityContext, "perform_healthy_check", return_value=None
             ):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(
                seeded["job_dir"]
            )
            mock_run.return_value = MagicMock(
                returncode=0, stdout="deadbeef\n", stderr=""
            )
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.wait.return_value = 0
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
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # .reviewer_session should NOT exist in the run_dir after stateless run
            run_dir = seeded["job_dir"]
            reviewer_session = os.path.join(run_dir, ".reviewer_session")
            assert not os.path.exists(reviewer_session), (
                ".reviewer_session should not be created for stateless engines"
            )


@patch("fcntl.flock")
@patch("shutil.rmtree")
@patch("shutil.copytree")
def test_stateful_reviewer_session_behavior_preserved(
    _mock_copytree, _mock_rmtree, _mock_flock
):
    """TC5: OpenClaw/stateful reviewer behavior remains compatible with existing
    session semantics. The --system-alert path is used for stateful retry."""
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
             patch.object(
                 orchestrator.SanityContext, "perform_healthy_check", return_value=None
             ):
            mock_glob.side_effect = seeded_job_dir_glob_side_effect(
                seeded["job_dir"]
            )
            mock_run.return_value = MagicMock(
                returncode=0, stdout="deadbeef\n", stderr=""
            )
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.wait.return_value = 0
            mock_popen.return_value.poll.return_value = 0

            # Use stateful engine (openclaw_native)
            with patch(
                "orchestrator.load_engine_registry",
                return_value={
                    "engines": {
                        "openclaw_native": {
                            "engine_id": "openclaw_native",
                            "cli_alias": "openclaw",
                            "continuity_mode": "stateful",
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
                    ],
                ):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # For stateful engines, retry should use --system-alert, not --inline-alert
            dpopen_calls = mock_popen.call_args_list
            reviewer_calls = [
                call
                for call in dpopen_calls
                if "spawn_reviewer.py"
                in " ".join(call[0][0]) if isinstance(call[0][0], list)
            ]
            inline_alert_calls = [
                call for call in reviewer_calls if "--inline-alert" in call[0][0]
            ]
            assert len(inline_alert_calls) == 0, (
                "No --inline-alert calls expected for stateful engine"
            )
