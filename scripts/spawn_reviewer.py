import argparse
import tempfile
import os
import sys
from agent_driver import invoke_agent, build_prompt
import config
import subprocess
import uuid
import fnmatch

def check_guardrails(workdir, pr_content, diff_files):
    guardrail_path = os.path.join(workdir, ".sdlc_guardrail")
    if not os.path.exists(guardrail_path):
        return None
        
    with open(guardrail_path, "r") as f:
        protected_patterns = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    if not protected_patterns:
        return None
        
    modified_files = set()
    for diff_file in diff_files:
        if os.path.exists(diff_file):
            with open(diff_file, "r") as f:
                for line in f:
                    if line.startswith("+++ b/") and not line.startswith("+++ b/dev/null"):
                        modified_files.add(line[6:].strip())
                    elif line.startswith("--- a/") and not line.startswith("--- a/dev/null"):
                        modified_files.add(line[6:].strip())
                    
    for mod_file in modified_files:
        # Check against patterns
        for pattern in protected_patterns:
            is_protected = False
            if pattern.endswith("/"):
                if mod_file.startswith(pattern):
                    is_protected = True
            else:
                if fnmatch.fnmatch(mod_file, pattern):
                    is_protected = True
                    
            if is_protected:
                # If explicitly authorized in PR content
                if mod_file not in pr_content:
                    return f"[ACTION_REQUIRED]: Guardrail violation detected. Unauthorized modification of protected file: {mod_file}"
                    
    return None

def main():
    parser = argparse.ArgumentParser(description="Spawn a reviewer agent.")
    parser.add_argument("--pr-file", required=False, help="Path to the PR Contract file")
    parser.add_argument("--prd-file", required=False, default="PRD.md", help="Path to the PRD file")
    parser.add_argument("--diff-target", required=False, help="Git diff target range (e.g., base_hash..latest_hash)")
    parser.add_argument("--override-diff-file", help="Override the diff file and skip git diff", default=None)
    parser.add_argument("--job-dir", required=False, default=".", help="Working directory for the Reviewer to generate artifacts")
    parser.add_argument("--workdir", required=False, help="Working directory lock")
    parser.add_argument("--out-file", default="review_report.json", help="Path to write the review report")
    parser.add_argument("--global-dir", required=False, help="Global directory for templates/playbooks")
    parser.add_argument("--run-dir", default=".", help="Run directory for artifacts")
    parser.add_argument("--system-alert", help="Send a system alert to the existing reviewer session", default=None)
    parser.add_argument("--engine", choices=["openclaw", "gemini"], default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE), help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})")
    parser.add_argument("--model", default=os.environ.get("SDLC_MODEL", config.DEFAULT_GEMINI_MODEL), help=f"Model to use when --engine is gemini (default: {config.DEFAULT_GEMINI_MODEL})")
    
    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    args = parser.parse_args()

    if isinstance(args.engine, str) and args.engine != os.environ.get("LLM_DRIVER"):
        os.environ["LLM_DRIVER"] = args.engine
    if isinstance(args.model, str) and args.model != os.environ.get("SDLC_MODEL"):
        os.environ["SDLC_MODEL"] = args.model

    session_file = os.path.join(args.run_dir, ".reviewer_session")

    if args.system_alert:
        if not os.path.exists(session_file):
            print(f"[FATAL] Session file {session_file} not found. Cannot send system alert.", file=sys.stderr)
            sys.exit(1)
        with open(session_file, "r") as sf:
            session_id = sf.read().strip()
        
        cmd = ["openclaw", "agent", "--session-id", session_id, "-m", args.system_alert]
        print(f"[reviewer] Sending system alert to session {session_id}")
        
        if os.environ.get("SDLC_TEST_MODE") == "true":
            with open(os.path.join(args.run_dir, args.out_file), "w") as rf:
                rf.write('```json\n{"status": "APPROVED", "comments": "Mock LGTM from alert"}\n```')
            print('{"status": "mock_success", "role": "reviewer_alert"}')
            sys.exit(0)
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[FATAL] System alert failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    if not args.workdir or not args.pr_file or not args.diff_target:
        print("[FATAL] --workdir, --pr-file, and --diff-target are required when not using --system-alert", file=sys.stderr)
        sys.exit(1)

    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    # Production mode
    if not os.path.exists(args.pr_file):
        print(f"Error: PR file not found: {args.pr_file}")
        sys.exit(1)
        
    with open(args.pr_file, "r") as f:
        pr_content = f.read()
        
    import re
    pr_num = 5
    match = re.search(r'PR_0*(\d+)', os.path.basename(args.pr_file))
    if match:
        pr_num = int(match.group(1))

    if args.override_diff_file:
        diff_file = args.override_diff_file
    else:
        diff_file = os.path.join(args.run_dir, "current_review.diff")

    if not args.override_diff_file:
        diff_cmd = f"git diff {args.diff_target} --no-color > {diff_file}"
        subprocess.run(diff_cmd, shell=True)
            
        baseline_file = os.path.join(args.run_dir, "baseline_commit.txt")
        if os.path.exists(baseline_file):
            with open(baseline_file, "r") as f:
                baseline_hash = f.read().strip()
            history_cmd = f"git log -p {baseline_hash}..HEAD > {os.path.join(args.run_dir, 'recent_history.diff')}"
        else:
            history_depth = max(5, pr_num)
            history_cmd = f"git log -n {history_depth} -p {args.diff_target} > {os.path.join(args.run_dir, 'recent_history.diff')}"
        subprocess.run(history_cmd, shell=True)
        
    guardrail_violation = check_guardrails(workdir, pr_content, [os.path.join(workdir, diff_file)])
    if guardrail_violation:
        print(f"[Reviewer Guardrail] Fast-failing PR due to guardrail violation.")
        with open(os.path.join(args.run_dir, args.out_file), "w") as rf:
            rf.write(guardrail_violation)
        if os.environ.get("SDLC_TEST_MODE") == "true":
            print('{"status": "mock_success", "role": "reviewer_guardrail"}')
            sys.exit(0)
        sys.exit(0)

    SDLC_ROOT = os.path.dirname(RUNTIME_DIR)
    template_content = ""

    playbook_path = os.path.join(SDLC_ROOT, "playbooks", "reviewer_playbook.md")
    playbook_content = ""
    if os.path.exists(playbook_path):
        with open(playbook_path, "r") as f:
            playbook_content = f.read()

    task_string = build_prompt("reviewer",
        workdir=workdir,
        playbook_content=playbook_content,
        pr_content=pr_content,
        pr_file=os.path.abspath(args.pr_file) if args.pr_file else "",
        prd_file=os.path.abspath(args.prd_file) if args.prd_file else "",
        diff_file=diff_file,
        out_file=os.path.abspath(os.path.join(args.run_dir, args.out_file)), run_dir=args.run_dir,
        template_content=template_content
    )
    

    import time
    session_id = f"subtask-{uuid.uuid4().hex[:8]}"
    
    
    # SCAFFOLDING
    review_report_path = os.path.join(args.run_dir, args.out_file)
    template_file_path = os.path.join(SDLC_ROOT, "TEMPLATES", "Review_Report.json.template")
    if os.path.exists(template_file_path):
        with open(template_file_path, "r") as tf:
            scaffold_content = tf.read()
    else:
        scaffold_content = '{\n  "overall_assessment": "NOT_STARTED",\n  "executive_summary": "Waiting for agent processing...",\n  "findings": []\n}'
        
    with open(review_report_path, "w") as f:
        f.write(scaffold_content)

    if os.environ.get("SDLC_TEST_MODE") == "true":
        os.makedirs("tests", exist_ok=True)
        with open("tests/tool_calls.log", "w") as tf:
            tf.write(task_string)
        # Mock LLM writing the report (we only do this if we are not testing failure scenarios)
        # Wait, if we mock it directly here, we might bypass the rigid verification tests if the test wants to check failures.
        # Actually, let's keep the mock writing but only if a test env var like SDLC_MOCK_REVIEWER_FAILURE is not set.
        if os.environ.get("SDLC_MOCK_REVIEWER_FAILURE") == "true":
            # Don't update the file, leave it as NOT_STARTED
            pass
        elif os.environ.get("SDLC_MOCK_REVIEWER_INVALID_JSON") == "true":
            with open(review_report_path, "w") as rf:
                rf.write('invalid json')
        else:
            with open(review_report_path, "w") as rf:
                rf.write('{"overall_assessment": "APPROVED", "comments": "Mock LGTM"}')
        print('{"status": "mock_success", "role": "reviewer"}')
        # We DO NOT sys.exit(0) here, we want verification to run!
    else:
        with open(session_file, "w") as sf:
            sf.write(session_id)
            
        result = invoke_agent(task_string, session_key=session_id, role="reviewer")

    # Removed stdout overwrite as agent writes directly to file

    # VERIFICATION
    import json
    if not os.path.exists(review_report_path):
        print(f"[FATAL] The Reviewer agent failed to generate the physical '{args.out_file}'. This is a severe process violation.", file=sys.stderr)
        sys.exit(1)

    try:
        with open(review_report_path, "r") as f:
            data = json.load(f)
            if data.get("overall_assessment") == "NOT_STARTED":
                print("[FATAL] The Reviewer agent failed to change overall_assessment from NOT_STARTED. Audit failed.", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"[FATAL] Invalid JSON in review report: {e}", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("SDLC_TEST_MODE") == "true":
        sys.exit(0)

if __name__ == "__main__":
    main()
