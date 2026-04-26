import os
import subprocess
import tempfile
import json
import pytest

SDLC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPAWN_AUDITOR = os.path.join(SDLC_ROOT, "scripts", "spawn_auditor.py")

@pytest.fixture
def run_dir(tmp_path):
    return tmp_path

@pytest.fixture
def valid_prd(tmp_path):
    prd_path = tmp_path / "valid_prd.md"
    prd_path.write_text("""
# 1. Context & Problem
# 2. Requirements & User Stories
# 3. Architecture & Technical Strategy
# 4. Acceptance Criteria
# 5. Overall Test Strategy
# 6. Framework Modifications
# 7. Hardcoded Content
""")
    return str(prd_path)

@pytest.fixture
def invalid_prd(tmp_path):
    prd_path = tmp_path / "invalid_prd.md"
    prd_path.write_text("""
# 1. Context & Problem
""")
    return str(prd_path)

def test_auditor_uses_envelope_assembler(run_dir, valid_prd):
    env = os.environ.copy()
    env["SDLC_TEST_MODE"] = "true"
    env["SDLC_RUN_DIR"] = str(run_dir)
    
    res = subprocess.run(
        ["python3", SPAWN_AUDITOR, "--prd-file", valid_prd, "--workdir", str(run_dir), "--channel", "test:channel", "--enable-exec-from-workspace"],
        env=env,
        capture_output=True,
        text=True
    )
    
    assert res.returncode == 0
    
    log_file = os.path.join(str(run_dir), "tests", "auditor_task_string.log")
    assert os.path.exists(log_file)
    with open(log_file, "r") as f:
        task_string = f.read()
        
    assert "# EXECUTION CONTRACT" in task_string
    assert "# REFERENCE INDEX" in task_string
    assert "# FINAL CHECKLIST" in task_string

def test_auditor_artifacts_are_saved(run_dir, valid_prd):
    env = os.environ.copy()
    env["SDLC_TEST_MODE"] = "true"
    env["SDLC_RUN_DIR"] = str(run_dir)
    
    subprocess.run(
        ["python3", SPAWN_AUDITOR, "--prd-file", valid_prd, "--workdir", str(run_dir), "--channel", "test:channel", "--enable-exec-from-workspace"],
        env=env,
        capture_output=True,
        text=True
    )
    
    debug_dir = os.path.join(str(run_dir), "auditor_debug")
    assert os.path.exists(debug_dir)
    assert os.path.exists(os.path.join(debug_dir, "startup_packet.json"))
    assert os.path.exists(os.path.join(debug_dir, "rendered_prompt.txt"))

def test_preflight_checks_remain(run_dir, invalid_prd):
    env = os.environ.copy()
    env["SDLC_TEST_MODE"] = "true"
    env["SDLC_RUN_DIR"] = str(run_dir)
    
    res = subprocess.run(
        ["python3", SPAWN_AUDITOR, "--prd-file", invalid_prd, "--workdir", str(run_dir), "--channel", "test:channel", "--enable-exec-from-workspace"],
        env=env,
        capture_output=True,
        text=True
    )
    
    assert res.returncode == 0 # Boss Mandate: sys.exit(0) for rejection to prevent LLM YOLO retry
    assert "REJECTED: PRD structure does not match the mandatory template. Missing sections:" in res.stdout
    assert "2. Requirements & User Stories" in res.stdout
