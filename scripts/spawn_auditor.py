#!/usr/bin/env python3
import argparse
import os
import sys
import uuid
import time

# Dynamic module resolution for monorepo development vs production deployment
current_dir = os.path.dirname(os.path.abspath(__file__))
import sys
sys.path.insert(0, current_dir)
import agent_driver
from agent_driver import invoke_agent, build_prompt

def main():
    parser = argparse.ArgumentParser(description="Spawn an Auditor agent.")
    parser.add_argument("--prd-file", required=True, help="Path to the PRD file")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    
    args = parser.parse_args()
    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    prd_file_abs = os.path.abspath(args.prd_file)
    if not os.path.exists(prd_file_abs):
        print(f"Error: PRD file not found: {prd_file_abs}")
        sys.exit(1)

    base_dir = os.path.dirname(current_dir)
    task_string = build_prompt("auditor",
        workdir=workdir,
        prd_file=prd_file_abs,
        base_dir=base_dir
    )
    


    test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"
    if test_mode:
        os.makedirs("tests", exist_ok=True)
        with open("tests/auditor_task_string.log", "w") as f:
            f.write(task_string)
        if "REJECT" in os.environ.get("MOCK_AUDIT_RESULT", ""):
            print('{"status": "REJECTED", "comments": "Mock rejected"}')
        else:
            print('{"status": "APPROVED", "comments": "Mock approved"}')
        sys.exit(0)

    print(f"🚀 Launching Agentic PRD Auditor on {args.prd_file}...")
    session_id = f"prd_auditor_{int(time.time())}"
    invoke_agent(task_string, session_key=session_id, role="auditor")

if __name__ == "__main__":
    main()
