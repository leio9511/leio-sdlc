import sys, os; sys.path.insert(0, os.path.abspath("scripts"))
import pytest
import os
import tempfile
import subprocess
import json
import shutil

def test_spawn_planner_uses_envelope():
    # Expected: When spawn_planner.py is invoked normally in test mode, the logged task_string uses the new envelope headers and does not have giant inlined PRD text.
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create dummy SDLC structure to bypass checks
        sdlc_root = os.path.join(tmpdir, "leio-sdlc")
        os.makedirs(os.path.join(sdlc_root, "scripts"))
        os.makedirs(os.path.join(sdlc_root, "TEMPLATES"))
        os.makedirs(os.path.join(sdlc_root, "playbooks"))
        
        script_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "spawn_planner.py"))
        planner_env_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "planner_envelope.py"))
        agent_driver_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "agent_driver.py"))
        config_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "config.py"))
        
        # We'll just run the actual script from the actual location, but workdir will be our tmpdir.
        # Wait, if we run the actual script, SDLC_ROOT is computed from script's __file__. So we don't need to fake SDLC_ROOT.
        
        prd_file = os.path.join(tmpdir, "PRD_Test.md")
        with open(prd_file, "w") as f:
            f.write("# Massive PRD content\n" * 100)
            
        run_dir = os.path.join(tmpdir, ".sdlc_runs", "test_proj", "PRD_Test")
        os.makedirs(run_dir, exist_ok=True)
        
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        # Disable workspace validation for the test
        
        subprocess.run([
            "python3", script_source,
            "--prd-file", prd_file,
            "--workdir", tmpdir,
            "--run-dir", run_dir,
            "--enable-exec-from-workspace"
        ], env=env, check=True)
        
        task_string_file = os.path.join(run_dir, "tests", "task_string.log")
        assert os.path.exists(task_string_file)
        
        with open(task_string_file, "r") as f:
            content = f.read()
            
        assert "# EXECUTION CONTRACT" in content
        assert "Massive PRD content" not in content

def test_spawn_planner_slice_uses_envelope():
    # Expected: Slice mode generates the envelope-based prompt, includes the `insert-after` clause, and creates debug artifacts.
    with tempfile.TemporaryDirectory() as tmpdir:
        prd_file = os.path.join(tmpdir, "PRD_Test3.md")
        with open(prd_file, "w") as f:
            f.write("# Mock PRD\n")
            
        failed_pr_file = os.path.join(tmpdir, "PR_002_failed.md")
        with open(failed_pr_file, "w") as f:
            f.write("# Failed PR content\n")
            
        run_dir = os.path.join(tmpdir, ".sdlc_runs", "test_proj", "PRD_Test3")
        os.makedirs(run_dir, exist_ok=True)
        
        script_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "spawn_planner.py"))
        
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        
        subprocess.run([
            "python3", script_source,
            "--prd-file", prd_file,
            "--workdir", tmpdir,
            "--run-dir", run_dir,
            "--slice-failed-pr", failed_pr_file,
            "--enable-exec-from-workspace"
        ], env=env, check=True)
        
        task_string_file = os.path.join(run_dir, "tests", "task_string.log")
        assert os.path.exists(task_string_file)
        
        with open(task_string_file, "r") as f:
            content = f.read()
            
        assert "# EXECUTION CONTRACT" in content
        assert "You MUST use the exact same `--insert-after 002` value" in content
        assert "failed_pr_contract" in content
        assert os.path.abspath(failed_pr_file) in content
        assert '"required": true' in content
        assert '"priority": 1' in content
        
        debug_dir = os.path.join(run_dir, "planner_debug")
        assert os.path.exists(debug_dir)
        startup_packet = os.path.join(debug_dir, "startup_packet.json")
        assert os.path.exists(startup_packet)
        with open(startup_packet, "r") as f:
            packet = json.load(f)
        refs_by_id = {ref["id"]: ref for ref in packet["reference_index"]}
        assert refs_by_id["failed_pr_contract"] == {
            "id": "failed_pr_contract",
            "kind": "pr_contract",
            "path": os.path.abspath(failed_pr_file),
            "required": True,
            "priority": 1,
            "purpose": "failed_slice_boundary_source",
        }
        assert "You MUST use the exact same `--insert-after 002` value" in "\n".join(packet["execution_contract"])

def test_spawn_planner_saves_artifacts():
    # Expected: The planner_debug artifacts are correctly persisted in the out_dir during a standard spawn_planner.py run.
    with tempfile.TemporaryDirectory() as tmpdir:
        prd_file = os.path.join(tmpdir, "PRD_Test2.md")
        with open(prd_file, "w") as f:
            f.write("# Mock PRD\n")
            
        run_dir = os.path.join(tmpdir, ".sdlc_runs", "test_proj", "PRD_Test2")
        os.makedirs(run_dir, exist_ok=True)
        
        script_source = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "spawn_planner.py"))
        
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        
        subprocess.run([
            "python3", script_source,
            "--prd-file", prd_file,
            "--workdir", tmpdir,
            "--run-dir", run_dir,
            "--enable-exec-from-workspace"
        ], env=env, check=True)
        
        debug_dir = os.path.join(run_dir, "planner_debug")
        assert os.path.exists(debug_dir)
        assert os.path.exists(os.path.join(debug_dir, "startup_packet.json"))
        assert os.path.exists(os.path.join(debug_dir, "startup_prompt.txt"))
        assert os.path.exists(os.path.join(debug_dir, "scaffold_contract.txt"))

from unittest.mock import patch, MagicMock
import glob



def test_planner_success_requires_generated_artifacts():
    import glob as real_glob_module
    _orig_glob = real_glob_module.glob

    with tempfile.TemporaryDirectory() as tmpdir:
        job_dir = os.path.join(tmpdir, "job_dir")
        os.makedirs(job_dir)
        with patch("sys.argv", ["orchestrator.py", "--workdir", tmpdir, "--prd-file", "dummy.md", "--force-replan", "false", "--enable-exec-from-workspace"]), \
             patch("orchestrator.dpopen") as mock_dpopen, \
             patch("orchestrator.glob.glob") as mock_glob, \
             patch("git_utils.check_git_boundary"), \
             patch("orchestrator.os.path.exists", side_effect=lambda path, _orig=os.path.exists: True if path in [job_dir, tmpdir] else _orig(path)), \
             patch("orchestrator.notify_channel"), \
             patch("orchestrator.subprocess.run"), \
             patch("orchestrator.drun", side_effect=Exception("Break loop")), \
             patch("orchestrator.sys.exit") as mock_exit:
             
             mock_proc = MagicMock()
             mock_proc.returncode = 0
             mock_dpopen.return_value = mock_proc
             
             def mock_glob_side_effect(pattern, *args, **kwargs):
                 if pattern.endswith("*.md"):
                     return [os.path.join(job_dir, "PR_mock.md")]
                 return _orig_glob(pattern, *args, **kwargs)
             
             mock_glob.side_effect = mock_glob_side_effect
             mock_exit.side_effect = SystemExit(1)
             
             import orchestrator
             try:
                 orchestrator.main()
             except Exception as e:
                 if str(e) != "Break loop" and not isinstance(e, SystemExit):
                     raise
             
             mock_exit.assert_not_called()

def test_planner_fails_without_artifacts_despite_stdout():
    with tempfile.TemporaryDirectory() as tmpdir:
        job_dir = os.path.join(tmpdir, "job_dir")
        os.makedirs(job_dir)
        with patch("sys.argv", ["orchestrator.py", "--workdir", tmpdir, "--prd-file", "dummy.md", "--force-replan", "false", "--enable-exec-from-workspace"]), \
             patch("orchestrator.dpopen") as mock_dpopen, \
             patch("orchestrator.glob.glob", return_value=[]), \
             patch("git_utils.check_git_boundary"), \
             patch("orchestrator.os.path.exists", side_effect=lambda path, _orig=os.path.exists: True if path in [job_dir, tmpdir] else _orig(path)), \
             patch("orchestrator.notify_channel"), \
             patch("orchestrator.subprocess.run"), \
             patch("orchestrator.sys.exit") as mock_exit:
             
             mock_proc = MagicMock()
             mock_proc.returncode = 0
             mock_dpopen.return_value = mock_proc
             mock_exit.side_effect = SystemExit(1)
             
             import orchestrator
             try:
                 orchestrator.main()
             except SystemExit:
                 pass
             
             mock_exit.assert_called_with(1)
