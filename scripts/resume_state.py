import json
import os
from datetime import datetime, timezone

def write_resume_state(run_dir, state, baseline_commit, current_pr_path=None, current_branch=None, recovery_mode="mainline", split_allowed=False):
    valid_states = {
        "PLANNER_ACTIVE", "CODER_ACTIVE", "REVIEWER_ACTIVE", 
        "VERIFIER_ACTIVE", "UAT_RECOVERY_ACTIVE", "COMPLETED_PASS", 
        "WITHDRAWN", "BLOCKED"
    }
    if state not in valid_states:
        raise ValueError(f"Invalid state: {state}")
    
    valid_modes = {"mainline", "uat_recovery", "split"}
    if recovery_mode not in valid_modes:
        raise ValueError(f"Invalid recovery mode: {recovery_mode}")

    if not isinstance(split_allowed, bool):
        raise ValueError("splitAllowed must be a boolean")

    state_data = {
        "state": state,
        "currentPrPath": current_pr_path,
        "currentBranch": current_branch,
        "baselineCommit": baseline_commit,
        "recoveryMode": recovery_mode,
        "splitAllowed": split_allowed,
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    
    state_file = os.path.join(run_dir, "resume_state.json")
    with open(state_file, "w") as f:
        json.dump(state_data, f, indent=4)

def get_baseline_commit(run_dir):
    try:
        with open(os.path.join(run_dir, "baseline_commit.txt"), "r") as f:
            return f.read().strip()
    except Exception:
        return ""
