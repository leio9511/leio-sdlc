"""
PR-004: Planner UAT and Split Visibility Tests
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))

import orchestrator

@pytest.fixture
def mock_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.makedirs(os.path.join(temp_dir, ".git"), exist_ok=True)
        yield temp_dir

def _base_drun_result(stdout="", returncode=0, stderr=""):
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = stderr
    return result

# ---------------------------------------------------------------------------
# Test Case 1: test_planner_split_notifications
# ---------------------------------------------------------------------------
def test_planner_split_notifications(mock_env):
    mock_workdir = mock_env
    run_dir = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd")
    os.makedirs(run_dir, exist_ok=True)
    
    prd_path = os.path.join(mock_workdir, "dummy_prd.md")
    Path(prd_path).write_text("# Dummy PRD", encoding="utf-8")
    
    pr_path = os.path.join(run_dir, "PR_001_Test.md")
    Path(pr_path).write_text("---\nstatus: blocked_fatal\nslice_depth: 1\n---\n# Test", encoding="utf-8")
    
    with open(os.path.join(run_dir, "resume_state.json"), "w") as f:
        json.dump({
            "state": "CODER_ACTIVE",
            "currentPrPath": pr_path,
            "currentBranch": "feature/test",
            "baselineCommit": "dummy_hash",
            "recoveryMode": "mainline",
            "splitAllowed": True,
            "updatedAt": "2023-01-01T00:00:00Z"
        }, f)
        
    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.drun") as mock_drun, \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun
        
        # Mock planner execution to create 2 slices
        def mock_dpopen_side_effect(cmd, *args, **kwargs):
            Path(os.path.join(run_dir, "PR_002_Slice1.md")).write_text("Slice 1", encoding="utf-8")
            Path(os.path.join(run_dir, "PR_003_Slice2.md")).write_text("Slice 2", encoding="utf-8")
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            return mock_proc
            
        mock_dpopen.side_effect = mock_dpopen_side_effect

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir", mock_workdir,
                    "--prd-file", prd_path,
                    "--split",
                    "--channel", "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir", mock_workdir,
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        calls = mock_notify.call_args_list
        event_types = [c[0][2] for c in calls]
        assert "planner_split_start" in event_types
        assert "planner_split_complete" in event_types

# ---------------------------------------------------------------------------
# Test Case 2: test_uat_recovery_plan_start
# ---------------------------------------------------------------------------
def test_uat_recovery_plan_start(mock_env):
    mock_workdir = mock_env
    run_dir = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd")
    os.makedirs(run_dir, exist_ok=True)
    
    prd_path = os.path.join(mock_workdir, "dummy_prd.md")
    Path(prd_path).write_text("# Dummy PRD", encoding="utf-8")
    
    pr_path = os.path.join(run_dir, "PR_001_Test.md")
    Path(pr_path).write_text("---\nstatus: closed\n---\n# Test", encoding="utf-8")
    
    uat_report_path = os.path.join(run_dir, "uat_report.json")
    
    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.drun") as mock_drun, \
         patch("agent_driver.send_ignition_handshake"):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
                if "get_next_pr.py" in cmd_str:
                    return _base_drun_result("[QUEUE_EMPTY]\n", 0)
                if "spawn_verifier.py" in cmd_str:
                    with open(uat_report_path, "w") as f:
                        json.dump({
                            "status": "NEEDS_FIX",
                            "verification_details": [{"status": "PARTIAL", "findings": "Missing logic"}]
                        }, f)
                    return _base_drun_result("", 0)
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun
        mock_dpopen.return_value.returncode = 0

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir", mock_workdir,
                    "--prd-file", prd_path,
                    "--force-replan", "false",
                    "--channel", "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir", mock_workdir,
                    "--max-prs-to-process", "1",
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        calls = mock_notify.call_args_list
        event_types = [c[0][2] for c in calls]
        assert "uat_recovery_plan_start" in event_types
        assert "uat_error" not in event_types

# ---------------------------------------------------------------------------
# Test Case 3: test_uat_recovery_exhausted_not_uat_error
# ---------------------------------------------------------------------------
def test_uat_recovery_exhausted_not_uat_error(mock_env):
    mock_workdir = mock_env
    run_dir = os.path.join(mock_workdir, ".sdlc_runs", os.path.basename(mock_workdir), "dummy_prd")
    os.makedirs(run_dir, exist_ok=True)
    
    prd_path = os.path.join(mock_workdir, "dummy_prd.md")
    Path(prd_path).write_text("# Dummy PRD", encoding="utf-8")
    
    pr_path = os.path.join(run_dir, "PR_001_Test.md")
    Path(pr_path).write_text("---\nstatus: closed\n---\n# Test", encoding="utf-8")
    
    uat_report_path = os.path.join(run_dir, "uat_report.json")
    
    with patch("orchestrator.SanityContext.perform_healthy_check"), \
         patch("orchestrator.notify_channel") as mock_notify, \
         patch("orchestrator.dpopen") as mock_dpopen, \
         patch("git_utils.check_git_boundary"), \
         patch("orchestrator.validate_prd_is_committed"), \
         patch("orchestrator.drun") as mock_drun, \
         patch("agent_driver.send_ignition_handshake"), \
         patch("orchestrator.resolve_retry_recovery_config", return_value={"max_uat_recovery_attempts": 0}):

        def dummy_drun(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    return _base_drun_result("master\n")
                if "get_next_pr.py" in cmd_str:
                    return _base_drun_result("[QUEUE_EMPTY]\n", 0)
                if "spawn_verifier.py" in cmd_str:
                    with open(uat_report_path, "w") as f:
                        json.dump({
                            "status": "NEEDS_FIX",
                            "verification_details": [{"status": "PARTIAL", "findings": "Missing logic"}]
                        }, f)
                    return _base_drun_result("", 0)
            return _base_drun_result()

        mock_drun.side_effect = dummy_drun

        try:
            with patch(
                "sys.argv",
                [
                    "orchestrator.py",
                    "--workdir", mock_workdir,
                    "--prd-file", prd_path,
                    "--force-replan", "false",
                    "--channel", "test-channel",
                    "--enable-exec-from-workspace",
                    "--global-dir", mock_workdir,
                    "--max-prs-to-process", "1",
                ],
            ):
                orchestrator.main()
        except SystemExit:
            pass

        calls = mock_notify.call_args_list
        event_types = [c[0][2] for c in calls]
        assert "uat_recovery_exhausted" in event_types
        assert "uat_error" not in event_types
