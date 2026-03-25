#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
import uuid

def main():
    parser = argparse.ArgumentParser(description="Spawn an arbitrator agent.")
    parser.add_argument("--pr-file", required=True, help="Path to the PR Contract file")
    parser.add_argument("--diff-target", required=True, help="Git diff target range (e.g., origin/master..HEAD)")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    
    args = parser.parse_args()
    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    # Check test mode
    if os.environ.get("SDLC_TEST_MODE") == "true":
        print("[CONFIRM_REJECT]")
        sys.exit(0)

    if not os.path.exists(args.pr_file):
        print(f"Error: PR file not found: {args.pr_file}")
        sys.exit(1)
        
    with open(args.pr_file, "r") as f:
        pr_content = f.read()
        
    diff_file = "current_arbitration.diff"
    diff_cmd = f"git diff {args.diff_target} --no-color > {diff_file}"
    subprocess.run(diff_cmd, shell=True)

    task_string = (
        f"ATTENTION: Your root workspace is rigidly locked to {workdir}. "
        f"You are the Arbitrator. The Coder and Reviewer have reached an impasse after 5 rejections.\n\n"
        f"--- PR Contract ---\n"
        f"{pr_content}\n"
        f"-------------------\n\n"
        f"Use the `read` tool to read the file: {diff_file} \n"
        f"You MUST read 'review_report.txt' to understand the Reviewer's objections.\n"
        f"Your ONLY job is to output exactly one of these two tokens as the final word in your response:\n"
        f"1. [OVERRIDE_LGTM] - If you believe the code satisfies the contract and the Reviewer is being too pedantic.\n"
        f"2. [CONFIRM_REJECT] - If you agree with the Reviewer that the code is materially defective.\n\n"
        f"Use the `write` tool to save your final decision to '{workdir}/arbitration_report.txt' and include either [OVERRIDE_LGTM] or [CONFIRM_REJECT] in the file.\n"
    )
    
    session_id = f"subtask-{uuid.uuid4().hex[:8]}"
    cmd = ["openclaw", "agent", "--session-id", session_id, "-m", task_string]
    subprocess.run(cmd, capture_output=True, text=True)

    report_path = os.path.join(workdir, "arbitration_report.txt")
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            content = f.read()
        if "[OVERRIDE_LGTM]" in content:
            print("[OVERRIDE_LGTM]")
        elif "[CONFIRM_REJECT]" in content:
            print("[CONFIRM_REJECT]")
        else:
            print("[CONFIRM_REJECT]")
    else:
        print("[CONFIRM_REJECT]")

if __name__ == "__main__":
    main()
