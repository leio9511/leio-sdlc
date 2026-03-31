#!/usr/bin/env python3
import argparse
import os
import sys

# Dynamic module resolution for monorepo development vs production deployment
current_dir = os.path.dirname(os.path.abspath(__file__))
monorepo_scripts_dir = os.path.abspath(os.path.join(current_dir, "../../../scripts"))
if os.path.exists(os.path.join(monorepo_scripts_dir, "agent_driver.py")):
    sys.path.insert(0, monorepo_scripts_dir)

from agent_driver import invoke_agent, build_prompt
import uuid

def main():
    parser = argparse.ArgumentParser(description="Spawn a PM agent.")
    parser.add_argument("--prd-file", required=True, help="Path to the PRD file")
    parser.add_argument("--context-file", required=True, help="Path to the context/feedback file")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    
    args = parser.parse_args()
    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    if not os.path.exists(args.prd_file):
        print(f"Error: PRD file not found: {args.prd_file}")
        sys.exit(1)
        
    with open(args.prd_file, "r") as f:
        prd_content = f.read()
        
    with open(args.context_file, "r") as f:
        context_content = f.read()

    task_string = build_prompt("pm",
        prd_content=prd_content,
        context_content=context_content
    )
    
    if os.environ.get("SDLC_TEST_MODE") == "true":
        print('{"status": "mock_success", "role": "pm"}')
        sys.exit(0)

    session_id = f"pm-{uuid.uuid4().hex[:8]}"
    invoke_agent(task_string, session_key=session_id, role="pm")

if __name__ == "__main__":
    main()
