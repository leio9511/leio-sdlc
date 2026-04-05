#!/usr/bin/env python3
import argparse
import os
import sys
import uuid
import time

# Dynamic module resolution for monorepo development vs production deployment
current_dir = os.path.dirname(os.path.abspath(__file__))
# Production: agent_driver.py is in the same directory as prd_auditor.py
# Monorepo: agent_driver.py is in ../../../scripts
monorepo_scripts_dir = os.path.abspath(os.path.join(current_dir, "../../../scripts"))

if os.path.exists(os.path.join(current_dir, "agent_driver.py")):
    sys.path.insert(0, current_dir)
elif os.path.exists(os.path.join(monorepo_scripts_dir, "agent_driver.py")):
    sys.path.insert(0, monorepo_scripts_dir)
else:
    print(f"Error: agent_driver.py not found in {current_dir} or {monorepo_scripts_dir}", file=sys.stderr)
    sys.exit(1)

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

    task_string = build_prompt("auditor",
        workdir=workdir,
        prd_file=prd_file_abs,
        skill_dir=os.path.dirname(current_dir)
    )
    

    print(f"🚀 Launching Agentic PRD Auditor on {args.prd_file}...")
    session_id = f"prd_auditor_{int(time.time())}"
    invoke_agent(task_string, session_key=session_id, role="auditor")

if __name__ == "__main__":
    main()
