import pytest
import os
import subprocess
import json
import tempfile

def test_spawn_planner_uat_uses_envelope(tmp_path, monkeypatch):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    
    prd_file = tmp_path / "PRD.md"
    prd_file.write_text("# Mock PRD\n\nContent")
    
    uat_report_file = tmp_path / "uat_report.json"
    uat_report_file.write_text('{"missing": []}')
    
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    
    monkeypatch.setenv("SDLC_TEST_MODE", "true")
    
    result = subprocess.run([
        "python3", "scripts/spawn_planner.py", "--enable-exec-from-workspace",
        "--prd-file", str(prd_file),
        "--workdir", str(workdir),
        "--out-dir", str(out_dir),
        "--run-dir", str(out_dir),
        "--replan-uat-failures", str(uat_report_file)
    ], capture_output=True, text=True, cwd=str(os.getcwd()))
    
    assert result.returncode == 0, result.stderr + result.stdout
    
    task_string_log = out_dir / "tests" / "task_string.log"
    if not task_string_log.exists():
        task_string_log = workdir / "tests" / "task_string.log"
    assert task_string_log.exists()
    
    task_string = task_string_log.read_text()
    
    assert "# EXECUTION CONTRACT" in task_string
    assert "without replanning already-satisfied functionality" in task_string
    assert "uat_report" in task_string
    
    # check debug artifacts
    debug_dir = out_dir / "planner_debug"
    assert debug_dir.exists()
    assert (debug_dir / "startup_packet.json").exists()
