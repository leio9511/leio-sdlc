import pytest
import os
import sys
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath("scripts"))
from orchestrator import SanityContext

def test_sanity_audit_pass(tmp_path):
    if 'SDLC_TEST_MODE' in os.environ:
        del os.environ['SDLC_TEST_MODE']
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    baseline_file = job_dir / "baseline_commit.txt"
    baseline_file.write_text("1234567890abcdef")
    
    with patch("subprocess.run") as mock_run:
        mock_branch = MagicMock()
        mock_branch.stdout = "PRD_Test/PR_001\n"
        mock_branch.returncode = 0
        
        mock_merge = MagicMock()
        mock_merge.returncode = 0
        
        mock_run.side_effect = [mock_branch, mock_merge]
        
        ctx = SanityContext(str(tmp_path), str(job_dir), "PRD_Test", False)
        ctx.perform_healthy_check()  # Should not raise
        
def test_sanity_audit_missing_baseline(tmp_path, capsys):
    if 'SDLC_TEST_MODE' in os.environ:
        del os.environ['SDLC_TEST_MODE']
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    
    ctx = SanityContext(str(tmp_path), str(job_dir), "PRD_Test", False)
    with pytest.raises(SystemExit):
        ctx.perform_healthy_check()
    out, err = capsys.readouterr()
    assert "[FATAL_METADATA]" in out

def test_sanity_audit_missing_job_dir(tmp_path, capsys):
    if 'SDLC_TEST_MODE' in os.environ:
        del os.environ['SDLC_TEST_MODE']
    job_dir = tmp_path / "job_dir"
    
    ctx = SanityContext(str(tmp_path), str(job_dir), "PRD_Test", False)
    with pytest.raises(SystemExit):
        ctx.perform_healthy_check()
    out, err = capsys.readouterr()
    assert "[FATAL_METADATA]" in out

def test_sanity_audit_unreachable_head(tmp_path, capsys):
    if 'SDLC_TEST_MODE' in os.environ:
        del os.environ['SDLC_TEST_MODE']
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    baseline_file = job_dir / "baseline_commit.txt"
    baseline_file.write_text("1234567890abcdef")
    
    with patch("subprocess.run") as mock_run:
        mock_branch = MagicMock()
        mock_branch.stdout = "PRD_Test/PR_001\n"
        mock_branch.returncode = 0
        
        mock_merge = MagicMock()
        mock_merge.returncode = 1
        
        mock_run.side_effect = [mock_branch, mock_merge]
        
        ctx = SanityContext(str(tmp_path), str(job_dir), "PRD_Test", False)
        with pytest.raises(SystemExit):
            ctx.perform_healthy_check()
        out, err = capsys.readouterr()
        assert "[FATAL_METADATA] Current Git HEAD is not reachable from the baseline hash." in out
