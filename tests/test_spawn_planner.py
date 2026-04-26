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
