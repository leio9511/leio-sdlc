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
    parser.add_argument("--channel", required=False, help="Notification channel")
    
    args = parser.parse_args()
    
    if not args.channel:
        print("[ACTION REQUIRED FOR MANAGER] [FATAL] Channel handshake failed. You MUST provide a valid --channel parameter (e.g., slack:#XXXX) and retry.")
        sys.exit(1)

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
            output = '{"status": "REJECTED", "comments": "Mock rejected"}'
        else:
            output = '{"status": "APPROVED", "comments": "Mock approved"}'
        print(output)
    else:
        print(f"🚀 Launching Agentic PRD Auditor on {args.prd_file}...")
        session_id = f"prd_auditor_{int(time.time())}"
        _, output = invoke_agent(task_string, session_key=session_id, role="auditor", return_output=True)

    status = "UNKNOWN"
    if '{"status": "APPROVED"' in output or '"status":"APPROVED"' in output or '"status": "APPROVED"' in output:
        status = "APPROVED"
    elif '{"status": "REJECTED"' in output or '"status":"REJECTED"' in output or '"status": "REJECTED"' in output:
        status = "REJECTED"

    import json
    try:
        # Try to parse exact json
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', output, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{.*?\})', output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1).strip())
            status = data.get("status", status)
    except Exception:
        pass

    if status == "APPROVED":
        agent_driver.notify_channel(args.channel, "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": args.prd_file})
        print("[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD. Notify the Boss of the successful audit, then you MUST immediately halt all further operations and WAIT for explicit authorization to deploy.")
    else:
        agent_driver.notify_channel(args.channel, "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": args.prd_file})
        print("[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD. Report the rejection reasons to the Boss, then you MUST immediately halt all further operations and WAIT for explicit instructions.")

if __name__ == "__main__":
    main()
