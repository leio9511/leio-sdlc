#!/usr/bin/env python3
import argparse
import os
import sys
from agent_driver import invoke_agent, build_prompt
import subprocess
import uuid

def main():
    parser = argparse.ArgumentParser(description="Spawn an arbitrator agent.")
    parser.add_argument("--pr-file", required=True, help="Path to the PR Contract file")
    parser.add_argument("--diff-target", required=True, help="Git diff target range (e.g., origin/master..HEAD)")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument("--run-dir", default=".", help="Run directory for artifacts")
    
    args = parser.parse_args()
    # API Key Assignment
    try:
        import json
        from utils_api_key import assign_gemini_api_key
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "sdlc_config.json"))
        app_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                app_config = json.load(f)

        run_dir_val = getattr(args, "run_dir", os.environ.get("SDLC_RUN_DIR", "."))
        session_keys_path = os.path.join(run_dir_val, ".session_keys.json")
        session_name = os.path.basename(__file__).replace(".py", "")
        if getattr(args, "pr_file", None):
            session_name += "_" + os.path.basename(args.pr_file)

        assigned_key = assign_gemini_api_key(session_name, app_config, session_keys_path)
        if assigned_key and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = assigned_key
    except Exception as e:
        pass
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
        
    diff_file = os.path.join(args.run_dir, "current_arbitration.diff")
    diff_cmd = f"git diff {args.diff_target} --no-color > {diff_file}"
    subprocess.run(diff_cmd, shell=True)

    task_string = build_prompt("arbitrator",
        workdir=workdir,
        pr_content=pr_content,
        diff_file=diff_file,
        review_report_path=os.path.join(args.run_dir, "review_report.json"), run_dir=args.run_dir
    )
    
    session_id = f"subtask-{uuid.uuid4().hex[:8]}"
    result = invoke_agent(task_string, session_key=session_id, role='arbitrator')

    report_path = os.path.join(args.run_dir, "arbitration_report.txt")
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
