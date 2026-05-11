import pytest
import os
import sys
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.resume_state import write_resume_state

def test_write_resume_state_valid_schema(tmp_path):
    run_dir = str(tmp_path)
    
    write_resume_state(
        run_dir=run_dir,
        state="CODER_ACTIVE",
        baseline_commit="abc1234",
        current_pr_path="/some/pr.md",
        current_branch="feat/test",
        recovery_mode="mainline",
        split_allowed=True
    )
    
    state_file = os.path.join(run_dir, "resume_state.json")
    assert os.path.exists(state_file)
    
    with open(state_file, "r") as f:
        data = json.load(f)
        
    assert data["state"] == "CODER_ACTIVE"
    assert data["currentPrPath"] == "/some/pr.md"
    assert data["currentBranch"] == "feat/test"
    assert data["baselineCommit"] == "abc1234"
    assert data["recoveryMode"] == "mainline"
    assert data["splitAllowed"] is True
    assert "updatedAt" in data

def test_write_resume_state_invalid_state(tmp_path):
    with pytest.raises(ValueError, match="Invalid state: INVALID_STATE"):
        write_resume_state(str(tmp_path), "INVALID_STATE", "abc1234")

def test_write_resume_state_invalid_mode(tmp_path):
    with pytest.raises(ValueError, match="Invalid recovery mode: invalid_mode"):
        write_resume_state(str(tmp_path), "CODER_ACTIVE", "abc1234", recovery_mode="invalid_mode")

def test_write_resume_state_invalid_split(tmp_path):
    with pytest.raises(ValueError, match="splitAllowed must be a boolean"):
        write_resume_state(str(tmp_path), "CODER_ACTIVE", "abc1234", split_allowed="yes")

from unittest.mock import patch, MagicMock
def test_orchestrator_persists_checkpoints_correctly():
    import os

    # Static analysis: verify that orchestrator.py calls write_resume_state with the expected states.
    orchestrator_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "orchestrator.py")
    with open(orchestrator_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'write_resume_state(run_dir, "PLANNER_ACTIVE"' in content
    assert 'write_resume_state(run_dir, "CODER_ACTIVE"' in content
    assert 'write_resume_state(run_dir, "REVIEWER_ACTIVE"' in content
    assert 'write_resume_state(run_dir, "VERIFIER_ACTIVE"' in content
    assert 'write_resume_state(run_dir, "COMPLETED_PASS"' in content
    assert 'write_resume_state(job_dir, "WITHDRAWN"' in content or 'write_resume_state(run_dir, "WITHDRAWN"' in content
    assert 'write_resume_state(run_dir, "BLOCKED"' in content
    assert 'write_resume_state(run_dir, "UAT_RECOVERY_ACTIVE"' in content
