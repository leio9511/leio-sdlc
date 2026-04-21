import pytest
import os
import subprocess
import json
import tempfile

def test_planner_uses_uat_recovery_prompt(tmp_path, monkeypatch):
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
        "python3", "scripts/spawn_planner.py",
        "--prd-file", str(prd_file),
        "--workdir", str(workdir),
        "--out-dir", str(out_dir),
        "--replan-uat-failures", str(uat_report_file)
    ], capture_output=True, text=True, cwd=str(os.getcwd()))
    
    assert result.returncode == 0, result.stderr + result.stdout
    
    task_string_log = workdir / "tests" / "task_string.log"
    assert task_string_log.exists()
    
    task_string = task_string_log.read_text()
    
    planner_recovery_prompt = "作为一个架构师，不要重新规划已有的功能。请仔细阅读 UAT 报告中标记为 MISSING 的需求，生成专门针对这些遗漏点的新 Micro-PRs（例如 PR_UAT_Fix_1.md），确保不破坏现有代码。"
    
    assert planner_recovery_prompt in task_string
    assert "You are the leio-sdlc Planner." not in task_string

def test_planner_parses_uat_report(tmp_path, monkeypatch):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    
    prd_file = tmp_path / "PRD.md"
    prd_file.write_text("# Mock PRD\n\nContent")
    
    uat_report_file = tmp_path / "uat_report.json"
    mock_uat_report = '{"status": "NEEDS_FIX", "verification_details": [{"status": "MISSING", "requirement": "Auth"}]}'
    uat_report_file.write_text(mock_uat_report)
    
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    
    monkeypatch.setenv("SDLC_TEST_MODE", "true")
    
    result = subprocess.run([
        "python3", "scripts/spawn_planner.py",
        "--prd-file", str(prd_file),
        "--workdir", str(workdir),
        "--out-dir", str(out_dir),
        "--replan-uat-failures", str(uat_report_file)
    ], capture_output=True, text=True, cwd=str(os.getcwd()))
    
    assert result.returncode == 0, result.stderr + result.stdout
    
    task_string_log = workdir / "tests" / "task_string.log"
    assert task_string_log.exists()
    
    task_string = task_string_log.read_text()
    
    assert "--- UAT REPORT ---" in task_string
    assert mock_uat_report in task_string
