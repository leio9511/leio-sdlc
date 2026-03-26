#!/usr/bin/env python3
import argparse
import tempfile
import os
import sys
import subprocess
import time
from pathlib import Path
def extract_pr_id(pr_file_path):
    basename = os.path.basename(pr_file_path)
    if basename.startswith("PR_"):
        parts = basename.split("_")
        if len(parts) >= 2:
            return f"PR_{parts[1]}"
    return basename.split(".")[0]
def openclaw_agent_call(session_key, message):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="sdlc_prompt_", dir="/tmp", text=True)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(message)
        
        secure_msg = f"Read your complete task instructions from {path}. Do not modify this file."
        cmd = ["openclaw", "agent", "--session-id", session_key, "--message", secure_msg]
        
        for attempt in range(3):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return session_key
            else:
                if attempt < 2:
                    time.sleep(3 * (2 ** attempt))
                else:
                    print(f"Error: subprocess returned non-zero exit status {result.returncode}")
                    sys.exit(1)
    finally:
        if os.path.exists(path):
            os.remove(path)
    return None
def send_feedback(session_key, message):
    """Function to append reviewer feedback to the existing session."""
    openclaw_agent_call(session_key, message)
    print(f"Sent feedback to session {session_key}")
def handle_feedback_routing(workdir, feedback_file, task_string, pr_id):
    session_file = os.path.join(workdir, ".coder_session")
    session_key = f"sdlc_coder_{pr_id}"
    try:
        with open(feedback_file, "r") as f:
            feedback_content = f.read()
        msg = f"\n--- Revision Feedback ---\n{feedback_content}\n\nYou are in a revision loop. Your previous attempt was rejected. Address the feedback above and modify the codebase accordingly."
        
        if os.path.exists(session_file):
            send_feedback(session_key, msg)
            return True, session_key
        else:
            task_string += msg
            openclaw_agent_call(session_key, task_string)
            with open(session_file, "w") as f:
                f.write(session_key)
            print(f"Spawned new session {session_key} with feedback")
            return False, session_key
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
def main():
    parser = argparse.ArgumentParser(description="Spawn a coder subagent")
    parser.add_argument("--pr-file", required=True, help="Path to the PR Contract file")
    parser.add_argument("--prd-file", required=True, help="Path to the PRD file")
    parser.add_argument("--feedback-file", required=False, help="Path to the Review Report / Feedback file")
    parser.add_argument("--system-alert", required=False, help="System alert string (e.g. git status)")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument("--global-dir", required=False, help="Global directory for playbooks")
    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    args = parser.parse_args()
    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        if branch in ["master", "main"]:
            print("[FATAL] Branch Isolation Guardrail: Coder agent cannot be spawned on the 'master' or 'main' branch.", file=sys.stderr)
            print("[ACTION REQUIRED]: You must create and checkout a new feature branch before assigning work to the Coder.", file=sys.stderr)
            print("Fix this by executing: git checkout -b feature/<pr_name>", file=sys.stderr)
            sys.exit(1)
    except subprocess.CalledProcessError:
        pass
    if not os.path.exists(args.pr_file):
        print(f"[Pre-flight Failed] Coder cannot start. PR Contract not found at '{args.pr_file}'. You must run spawn_planner.py first.")
        sys.exit(1)
    pr_id = extract_pr_id(args.pr_file)
    test_mode = os.environ.get("SDLC_TEST_MODE") == "true"
    if test_mode:
        log_entry = str({'tool': 'spawn_coder', 'args': {'pr_file': args.pr_file, 'prd_file': args.prd_file, 'feedback_file': args.feedback_file, 'workdir': workdir}})
        
        # Ensure tests dir exists
        Path("tests").mkdir(exist_ok=True)
        
        with open("tests/tool_calls.log", "a") as f:
            f.write(log_entry + "\n")
        
        print('{"status": "mock_success", "role": "coder", "sessionKey": "mock-session-key"}')
        sys.exit(0)
    else:
        try:
            with open(args.pr_file, "r") as f:
                pr_content = f.read()
            with open(args.prd_file, "r") as f:
                prd_content = f.read()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
            
        # Inject Coder Playbook (PRD_1005)
        RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
        global_dir = os.path.abspath(args.global_dir) if args.global_dir else os.path.dirname(RUNTIME_DIR)
        playbook_path = os.path.join(global_dir, "playbooks", "coder_playbook.md")
        playbook_content = ""
        if os.path.exists(playbook_path):
            with open(playbook_path, "r") as f:
                playbook_content = f.read()
        
        task_string = (
            f"ATTENTION: Your root workspace is rigidly locked to {workdir}. "
            f"You are strictly forbidden from reading, writing, or modifying files outside this absolute path. "
            f"Use explicit 'git add <file>' to stage changes safely within your directory.\n\n"
            f"You are strictly forbidden from manually editing the markdown file's `status` field.\n\n"
            f"--- CODER PLAYBOOK ---\n{playbook_content}\n\n"
            f"You are an autonomous Fat Coder. The PR Contract provides functional requirements, NOT exact file paths. YOU must search the workspace, read the code, and autonomously decide which files to modify to implement the feature. Prove your code works by writing and passing tests.\n\n--- PR Contract ({args.pr_file}) ---\n{pr_content}\n\n--- PRD ({args.prd_file}) ---\n{prd_content}\n"
        )
        
        session_file = os.path.join(workdir, ".coder_session")
        session_key = f"sdlc_coder_{pr_id}"
        
        if args.system_alert:
            msg = f"\n--- SYSTEM ALERT ---\nDirty git workspace detected!\n{args.system_alert}\n\nYou MUST clean up untracked artifacts using .gitignore or acknowledge them by writing {{\"dirty_acknowledged\": true}} to .coder_state.json. Ensure all your code changes for this PR are staged with explicit \`git add <file>\`."
            if os.path.exists(session_file):
                send_feedback(session_key, msg)
            else:
                task_string += msg
                openclaw_agent_call(session_key, task_string)
                with open(session_file, "w") as f:
                    f.write(session_key)
                print(f"Spawned new session {session_key} with system alert")
        elif args.feedback_file:
            handle_feedback_routing(workdir, args.feedback_file, task_string, pr_id)
        else:
            openclaw_agent_call(session_key, task_string)
            with open(session_file, "w") as f:
                f.write(session_key)
            print(f"Spawned new session {session_key}")
if __name__ == "__main__":
    main()
