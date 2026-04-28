#!/usr/bin/env python3
import argparse
import os
import sys
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
import agent_driver
from agent_driver import invoke_agent
from envelope_assembler import build_startup_envelope, render_envelope_to_prompt, save_envelope_artifacts

def main():
    parser = argparse.ArgumentParser(description="Spawn a UAT Verifier agent.")
    parser.add_argument("--prd-files", required=True, help="Comma-separated paths to PRDs")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument("--out-file", default="uat_report.json", help="Path to output JSON")
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass the workspace path check")
    
    args = parser.parse_args()
    import config
    from handoff_prompter import HandoffPrompter
    if not getattr(args, "enable_exec_from_workspace", False) and not sys.argv[0].startswith(getattr(config, "SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))):
        print(HandoffPrompter.get_prompt("startup_validation_failed"))
        sys.exit(1)
    # API Key Assignment
    from utils_api_key import setup_spawner_api_key
    setup_spawner_api_key(args, __file__)
    
    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    SDLC_ROOT = os.path.dirname(current_dir)
    playbook_path = os.path.join(SDLC_ROOT, "playbooks", "verifier_playbook.md")

    references = {
        "prd_files": args.prd_files,
        "playbook_path": playbook_path,
    }
    contract_params = {
        "output_file": os.path.abspath(args.out_file),
        "output_schema": {
            "status": "(PASS|NEEDS_FIX)",
            "executive_summary": "A concise summary of the UAT outcome.",
            "verification_details": [
                {
                    "requirement": "Description of the requirement extracted from the PRD(s).",
                    "status": "(IMPLEMENTED|MISSING|PARTIAL)",
                    "evidence": "File paths, code snippets, or tool output proving the status.",
                    "comments": "Any notes or suggestions for hotfixes if applicable.",
                }
            ],
        },
    }

    envelope = build_startup_envelope(
        role="verifier",
        workdir=workdir,
        out_dir=os.getcwd(),
        references=references,
        contract_params=contract_params
    )
    task_string = render_envelope_to_prompt(envelope)

    run_dir = os.environ.get("SDLC_RUN_DIR", ".")
    save_envelope_artifacts(
        role="uat",
        out_dir=run_dir,
        envelope=envelope,
        rendered_prompt=task_string,
        artifact_subdir="initial"
    )

    test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"
    if test_mode:
        import json
        run_dir = os.environ.get("SDLC_RUN_DIR", ".")
        os.makedirs(os.path.join(run_dir, "tests"), exist_ok=True)
        with open(os.path.join(run_dir, "tests", "verifier_task_string.log"), "w") as f:
            f.write(task_string)
            
        mock_result = os.environ.get("MOCK_VERIFIER_RESULT", '{"status": "PASS", "executive_summary": "Mock passed", "verification_details": []}')
        with open(os.path.abspath(args.out_file), "w") as f:
            f.write(mock_result)
        print(f"Mock UAT Verifier completed successfully. Report written to {args.out_file}")
    else:
        print(f"🚀 Launching Agentic UAT Verifier...")
        session_id = f"uat_verifier_{int(time.time())}"
        # The verifier agent is instructed in the prompt to use the 'write' tool to save the JSON directly.
        result = invoke_agent(task_string, session_key=session_id, role="verifier")
        
        # Verify that the output file was actually created by the agent
        if not os.path.exists(os.path.abspath(args.out_file)):
            print(f"Error: Verifier agent failed to produce {args.out_file}", file=sys.stderr)
            sys.exit(1)

        print(f"UAT Verifier completed successfully. Report written to {args.out_file}")

if __name__ == "__main__":
    main()
