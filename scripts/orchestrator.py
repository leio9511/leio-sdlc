#!/usr/bin/env python3
import os
import sys
from agent_driver import invoke_agent, build_prompt
proc = None
import glob
import subprocess
import re
import argparse
import uuid
import time
import fcntl
import signal
import traceback

# Global marker for Git Hook authentication (PRD-1012)
os.environ["SDLC_ORCHESTRATOR_RUNNING"] = "1"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from git_utils import safe_git_checkout, GitCheckoutError
from notification_formatter import format_notification
from handoff_prompter import HandoffPrompter

MAX_RUNTIME = int(os.environ.get("SDLC_TIMEOUT", 3600)) # 60 minutes default

import json

def dlog(msg):
    if os.environ.get("SDLC_DEBUG_MODE") == "1":
        print(f"DEBUG: {msg}")

def drun(cmd, **kwargs):
    debug = os.environ.get("SDLC_DEBUG_MODE") == "1"
    if debug:
        print(f"DEBUG [Subprocess]: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, **kwargs)
    if debug:
        print(f"DEBUG [Subprocess Return]: {res.returncode}")
        if hasattr(res, 'stdout') and isinstance(res.stdout, str) and res.stdout.strip():
            print(f"DEBUG [Subprocess Stdout]: {res.stdout.strip()}")
        if hasattr(res, 'stderr') and isinstance(res.stderr, str) and res.stderr.strip():
            print(f"DEBUG [Subprocess Stderr]: {res.stderr.strip()}")
    return res

def dpopen(cmd, **kwargs):
    if os.environ.get("SDLC_DEBUG_MODE") == "1":
        print(f"DEBUG [Subprocess Popen]: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.Popen(cmd, **kwargs)

def parse_affected_projects(prd_file):
    if not os.path.exists(prd_file):
        return []
    with open(prd_file, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'^\s*Affected_Projects:\s*\[(.*?)\]', content, re.MULTILINE | re.IGNORECASE)
    if match:
        projects_str = match.group(1)
        projects = [p.strip() for p in projects_str.split(',') if p.strip()]
        return sorted(projects)
    return []

def acquire_global_locks(projects, workdir):
    lock_dir = os.path.expanduser("~/.openclaw/workspace/locks")
    os.makedirs(lock_dir, exist_ok=True)
    acquired_locks = []
    fds = []
    
    for project in projects:
        lock_path = os.path.join(lock_dir, f"{project}.lock")
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired_locks.append(lock_path)
            fds.append(fd)
        except (BlockingIOError, IOError, OSError):
            print(f"[FATAL_LOCK] Failed to acquire global lock for project '{project}'.")
            # Rollback: Close and REMOVE all locks acquired in this batch
            for rollback_fd in reversed(fds):
                try:
                    fcntl.flock(rollback_fd, fcntl.LOCK_UN)
                    os.close(rollback_fd)
                except Exception:
                    pass
            for rollback_path in acquired_locks:
                try:
                    if os.path.exists(rollback_path):
                        os.remove(rollback_path)
                except OSError:
                    pass
            sys.exit(1)
            
    manifest_path = os.path.join(workdir, ".sdlc_lock_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({"locks": acquired_locks}, f)
        
    return acquired_locks, fds

def set_pr_status(pr_file, new_status):
    with open(pr_file, 'r', encoding='utf-8') as f:
        content = f.read()
    updated = re.sub(r'^status:\s*\S+', f'status: {new_status}', content, count=1, flags=re.MULTILINE)
    with open(pr_file, 'w', encoding='utf-8') as f:
        f.write(updated)
    # PRD 1060: PR status updates are now untracked artifacts to prevent pollution
    # subprocess.run(["git", "add", pr_file], check=False)
    # subprocess.run(["git", "-c", "sdlc.runtime=1", "commit", "-m", f"chore(state): update PR state to {new_status}"], check=False)

def get_pr_slice_depth(pr_file):
    with open(pr_file, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'slice_depth:\s*(\d+)', content)
    if match:
        return int(match.group(1))
    return 0

def teardown_coder_session(workdir):
    session_file = os.path.join(workdir, ".coder_session")
    if os.path.exists(session_file):
        with open(session_file, "r") as f:
            session_key = f.read().strip()
        if session_key:
            print(f"Tearing down coder session {session_key}")
        try:
            os.remove(session_file)
        except OSError:
            pass # Reaper safety check: process already reaped or pgid not found

def notify_channel(effective_channel, msg, event_type=None, context=None):
    if event_type:
        msg = format_notification(event_type, context or {})
    else:
        msg = f"🤖 [SDLC Engine] {msg}"
    if effective_channel:
        cmd = ["openclaw", "message", "send"]
        if ":" in effective_channel:
            parts = effective_channel.split(":")
            if len(parts) >= 2:
                cmd.extend(["--channel", parts[0]])
                cmd.extend(["-t", ":".join(parts[1:])])
        else:
            cmd.extend(["-t", effective_channel])
        cmd.extend(["-m", msg])
        
        if os.environ.get("SDLC_TEST_MODE") == "true":
            dlog(f"[notify_channel]: {' '.join(cmd)}")
            return
            
        drun(cmd, check=False)

import json


def validate_prd_is_committed(prd_file, workdir):
    prd_path_abs = os.path.abspath(prd_file)
    if os.path.exists(prd_path_abs):
        try:
            drun(["git", "ls-files", "--error-unmatch", prd_path_abs], check=True, capture_output=True, cwd=workdir)
        except subprocess.CalledProcessError:
            print(f"[SDLC Framework] PRD file '{prd_file}' is untracked. Auto-committing for ingestion.")
            drun(["git", "add", prd_path_abs], check=True, cwd=workdir)
            drun(["git", "-c", "sdlc.runtime=1", "commit", "-m", "docs(prd): auto-commit PRD"], check=True, cwd=workdir)

        status_out = drun(["git", "status", "--porcelain", prd_path_abs], capture_output=True, text=True, cwd=workdir).stdout.strip()
        if status_out:
            print(f"[SDLC Framework] PRD file '{prd_file}' has uncommitted changes. Auto-committing.")
            drun(["git", "add", prd_path_abs], check=True, cwd=workdir)
            drun(["git", "-c", "sdlc.runtime=1", "commit", "-m", "docs(prd): auto-commit PRD changes"], check=True, cwd=workdir)

def parse_review_verdict(content):
    """
    Parses structured JSON review status: {"status": "APPROVED", "comments": "..."}
    Matches the prompt given to the Reviewer.
    """
    try:
        # Search for code blocks or literal json
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{.*?\})', content, re.DOTALL)
        
        if json_match:
            data = json.loads(json_match.group(1).strip())
            return data.get("status")
    except (json.JSONDecodeError, AttributeError, ValueError):
        pass # Reaper safety check: process already reaped or pgid not found
    return None

def trigger_github_sync(workdir, effective_channel, pr_id):
    sync_script = os.path.expanduser("~/.openclaw/skills/leio-github-sync/scripts/sync.py")
    if os.path.exists(sync_script):
        notify_channel(effective_channel, "Synchronizing code to GitHub...", "github_sync_start", {"pr_id": pr_id})
        try:
            res = drun([sys.executable, sync_script, "--project-dir", workdir], capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                notify_channel(effective_channel, "GitHub sync complete.", "github_sync_complete", {"pr_id": pr_id})
            else:
                err_msg = res.stderr.strip() if res.stderr else "Non-zero exit code"
                print(f"[Warning] GitHub Sync failed: {err_msg}", file=sys.stderr)
                notify_channel(effective_channel, f"GitHub sync failed: {err_msg}", "github_sync_failed", {"pr_id": pr_id, "error": err_msg})
        except subprocess.TimeoutExpired:
            print("[Warning] GitHub Sync failed: Timeout", file=sys.stderr)
            notify_channel(effective_channel, "GitHub sync failed: Timeout", "github_sync_failed", {"pr_id": pr_id, "error": "Timeout"})
        except Exception as e:
            print(f"[Warning] GitHub Sync failed: {str(e)}", file=sys.stderr)
            notify_channel(effective_channel, f"GitHub sync failed: {str(e)}", "github_sync_failed", {"pr_id": pr_id, "error": str(e)})

def initialize_sandbox(workdir):
    exclude_path = os.path.join(workdir, ".git", "info", "exclude")
    if os.path.exists(os.path.dirname(exclude_path)):
        # Check if already excluded
        already_excluded = False
        if os.path.exists(exclude_path):
            with open(exclude_path, "r") as f:
                if ".sdlc_runs/" in f.read():
                    already_excluded = True
        
        if not already_excluded:
            with open(exclude_path, "a") as f:
                f.write("\n.sdlc_runs/\n")
            print(f"Initialized local sandbox: added .sdlc_runs/ to .git/info/exclude")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--prd-file", required=True)
    parser.add_argument("--max-prs-to-process", type=int, default=50)
    parser.add_argument("--coder-session-strategy", default="on-escalation", choices=["always", "per-pr", "on-escalation"])
    parser.add_argument("--force-replan", action="store_true")
    parser.add_argument("--channel", help="Notification channel")
    parser.add_argument("--global-dir", help="Global workspace path")
    parser.add_argument("--test-sleep", action="store_true")
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass # Reaper safety check: process already reaped or pgid not found the workspace path check")

    parser.add_argument("--cleanup", action="store_true", help="Lock-aware forensic quarantine of crashed orchestrator state")
    parser.add_argument("--debug", action="store_true", help="Enable debug trace logs")
    args = parser.parse_args()

    # Store debug mode in the application's configuration state
    os.environ["SDLC_DEBUG_MODE"] = "1" if args.debug else "0"

    if args.cleanup:
        # 1. Concurrency Guard (Crucial)
        lock_path = os.path.join(args.workdir, ".sdlc_repo.lock")
        try:
            f_lock = open(lock_path, "w")
            fcntl.flock(f_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError):
            print("[FATAL_LOCK] Cannot clean up while another SDLC pipeline is active.")
            sys.exit(1)
        
        # 2-7. Quarantine logic: Stage, WIP commit, rename, checkout master
        os.chdir(args.workdir)
        branch_res = drun(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch_output = branch_res.stdout.strip()
        if "/" in branch_output:
            parent_dir_name = branch_output.split('/')[0]
            job_dir_rel = os.path.join('.sdlc_runs', parent_dir_name)
            if os.path.exists(os.path.join(args.workdir, job_dir_rel)):
                drun(["git", "add", "-f", job_dir_rel], check=False)

        if branch_output in ["master", "main"]:
            print("Cannot quarantine master/main branch.")
            sys.exit(1)
            
        drun(["git", "add", "-A"], check=False)
        drun(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
        timestamp = int(time.time())
        drun(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
        drun(["git", "checkout", "master"], check=False)
        
        # 8. Targeted Artifact Obliteration (os.remove for daemon locks)
        for lockfile in [".coder_session", ".sdlc_repo.lock"]:
            try:
                os.remove(os.path.join(args.workdir, lockfile))
            except OSError:
                pass # Already deleted
        
        manifest_path = os.path.join(args.workdir, ".sdlc_lock_manifest.json")
        if os.path.exists(manifest_path):
            try:
                import json
                with open(manifest_path, "r") as f:
                    manifest_data = json.load(f)
                for lock_path in manifest_data.get("locks", []):
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except OSError:
                        pass
                os.remove(manifest_path)
            except Exception as e:
                print(f"[Warning] Failed to clean up manifest locks: {e}")

        sys.exit(0)

    if "/root/.openclaw/workspace/projects/" in os.path.abspath(__file__) and not args.enable_exec_from_workspace:
        print("[FATAL] Security Violation: This skill is executing from a restricted source directory. For your safety, execution is blocked unless authorized via --enable-exec-from-workspace.")
        print(HandoffPrompter.get_prompt("startup_validation_failed"))
        sys.exit(1)

    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    workdir = os.path.abspath(args.workdir)
    dlog(f"Workdir: {workdir}")
    from git_utils import check_git_boundary
    check_git_boundary(workdir)
    initialize_sandbox(workdir)
    global_dir = os.path.dirname(RUNTIME_DIR) if not args.global_dir else os.path.abspath(args.global_dir)
    os.chdir(workdir)

    validate_prd_is_committed(args.prd_file, workdir)
    dlog("Checking branch guardrail...")
    if os.environ.get("SDLC_BYPASS_BRANCH_CHECK") != "1":
        if not os.path.exists(".git"):
            print("[FATAL] Git Boundary Enforcement: workdir must contain a .git directory.")
            print(HandoffPrompter.get_prompt("invalid_git_boundary"))
            sys.exit(1)
        branch_output = drun(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        if branch_output not in ["master", "main"]:
            print(f"[FATAL] Orchestrator must be started from the master or main branch. Current: {branch_output}")
            print(HandoffPrompter.get_prompt("invalid_git_boundary"))
            sys.exit(1)

    affected_projects = parse_affected_projects(args.prd_file)
    if affected_projects:
        global_locks, global_fds = acquire_global_locks(affected_projects, workdir)
    else:
        global_locks, global_fds = [], []

    try:
        lock_path = os.path.join(workdir, ".sdlc_repo.lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[FATAL] Another SDLC pipeline is currently running. Concurrent execution is blocked.")
        print(HandoffPrompter.get_prompt("pipeline_locked"))
        sys.exit(1)

    if args.test_sleep:
        time.sleep(2)
        sys.exit(0)

    status_output = drun(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
    if status_output.strip(): dlog(f"Dirty status detected: {repr(status_output)}")
    if status_output.strip():
        print("[FATAL] Dirty Git Workspace detected!")
        print(HandoffPrompter.get_prompt("dirty_workspace"))
        sys.exit(1)

    effective_channel = args.channel or os.environ.get("OPENCLAW_SESSION_KEY") or os.environ.get("OPENCLAW_CHANNEL_ID")
    if not effective_channel and os.environ.get("SDLC_TEST_MODE") != "true":
        print("[FATAL] Missing channel parameter.")
        print(HandoffPrompter.get_prompt("missing_channel"))
        sys.exit(1)

    # --- IGNITION GUARDRAIL ---
    if effective_channel:
        cmd_handshake = ["openclaw", "message", "send"]
        if ":" in effective_channel:
            parts = effective_channel.split(":")
            if len(parts) >= 2:
                cmd_handshake.extend(["--channel", parts[0]])
                cmd_handshake.extend(["-t", ":".join(parts[1:])])
        else:
            cmd_handshake.extend(["-t", effective_channel])
        
        msg = format_notification("sdlc_handshake", {})
        cmd_handshake.extend(["-m", msg])
        
        if os.environ.get("SDLC_TEST_MODE") != "true":
            res = drun(cmd_handshake, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[FATAL] Invalid notification channel format. Failed to send handshake to '{effective_channel}'. Expected format e.g., slack:CXXXXXX", file=sys.stderr)
                if res.stderr: print(res.stderr.strip(), file=sys.stderr)
                print(HandoffPrompter.get_prompt("missing_channel"))
                sys.exit(1)
        else:
            print(f"DEBUG [Ignition Handshake]: {' '.join(cmd_handshake)}")
        if "invalid" in effective_channel:
            print(f"[FATAL] Invalid notification channel format. Failed to send handshake to '{effective_channel}'. Expected format e.g., slack:CXXXXXX", file=sys.stderr)
            print(HandoffPrompter.get_prompt("missing_channel"))
            sys.exit(1)
    # --------------------------

    prd_filename = os.path.basename(args.prd_file)
    base_name, _ = os.path.splitext(prd_filename)
    job_dir_rel = os.path.join(".sdlc_runs", base_name)
    job_dir = os.path.abspath(os.path.join(workdir, job_dir_rel))

    if os.path.exists(job_dir) and not args.force_replan:
        md_files = glob.glob(os.path.join(job_dir, "*.md"))
        if len(md_files) > 0:
            print("State 0: Existing PRs detected. Resuming queue...")
            dlog(f"Transitioning to State 0 for PRD {prd_filename} (resuming)")
            notify_channel(effective_channel, "Ignition: Resuming existing queue...", "sdlc_resume", {"prd_id": prd_filename})
    else:
        if args.force_replan and os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir)
        print("State 0: Auto-slicing PRD...")
        dlog(f"Transitioning to State 0 for PRD {prd_filename} (auto-slicing)")
        notify_channel(effective_channel, "Ignition: Starting new SDLC pipeline...", "sdlc_start", {"prd_id": prd_filename})
        notify_channel(effective_channel, "State 0: Auto-slicing PRD...", "slicing_start", {"prd_id": prd_filename})
        try:
            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--prd-file", args.prd_file, "--workdir", workdir, "--global-dir", global_dir], start_new_session=True)
            proc.wait()
            if proc.returncode != 0: raise subprocess.CalledProcessError(proc.returncode, "spawn_planner.py")
        except subprocess.CalledProcessError: pass # Reaper safety check: process already reaped or pgid not found
        if not os.path.exists(job_dir):
            print("[FATAL] Planner failed to generate any PRs.")
            print(HandoffPrompter.get_prompt("planner_failure"))
            sys.exit(1)
        md_files = glob.glob(os.path.join(job_dir, "*.md"))
        if len(md_files) == 0:
            print("[FATAL] Planner failed to generate any PRs.")
            print(HandoffPrompter.get_prompt("planner_failure"))
            sys.exit(1)
        notify_channel(effective_channel, "Slicing end.", "slicing_end", {"prd_id": prd_filename, "count": len(md_files)})


    proc = None

    def sig_handler(signum, frame):
        print(HandoffPrompter.get_prompt("fatal_interrupt"))
        raise SystemExit(1)
    
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    try:
        loops = 0
        while True:
            if args.max_prs_to_process > 0 and loops >= args.max_prs_to_process:
                print(f"Max runs reached. Exiting orchestrator.")
                break
            loops += 1
            md_files = glob.glob(os.path.join(job_dir, "*.md"))
            md_files.sort()
            current_pr = None
            for md_file in md_files:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if re.search(r'^status:\s*in_progress', content, re.MULTILINE):
                        current_pr = md_file
                        break
            if not current_pr:
                result = drun([sys.executable, os.path.join(RUNTIME_DIR, "get_next_pr.py"), "--workdir", workdir, "--job-dir", job_dir], capture_output=True, text=True)
                output = result.stdout.strip()
                if "[QUEUE_EMPTY]" in output or not output:
                    print("No open PRs found. Exiting.")
                    print(HandoffPrompter.get_prompt("happy_path"))
                    notify_channel(effective_channel, "Success: All PRs completed!", "all_done", {"prd_id": prd_filename})
                    sys.exit(0)
                current_pr = output.split('\n')[-1].strip()
                if not os.path.exists(current_pr):
                    print(HandoffPrompter.get_prompt("dead_end"))
                    sys.exit(1)
                set_pr_status(current_pr, "in_progress")

            if args.coder_session_strategy == "per-pr": teardown_coder_session(workdir)
            base_filename = os.path.splitext(os.path.basename(current_pr))[0]
            parent_dir_name = os.path.basename(os.path.dirname(os.path.abspath(current_pr)))
            branch_name = f"{parent_dir_name}/{base_filename}".replace(":", "_").replace(" ", "_").replace("?", "_")
            reset_count = 0
            pr_done = False
            while True:
                if pr_done: break
                status_result = drun(["git", "diff", "--cached", "--quiet"])
                if status_result.returncode != 0:
                    drun(["git", "-c", "sdlc.runtime=1", "commit", "-m", "docs(planner): auto-generated PR contracts"], check=True)
                print(f"State 2: Checking out branch {branch_name}")
                dlog(f"Transitioning to State 2: Checkout branch {branch_name} for PR {current_pr}")
                try:
                    branch_check = drun(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"])
                    if branch_check.returncode == 0: safe_git_checkout(branch_name)
                    else: safe_git_checkout(branch_name, create=True)
                except GitCheckoutError as e:
                    print(HandoffPrompter.get_prompt("git_checkout_error"))
                    sys.exit(1)
                rejection_count = 0
                state_5_trigger = False
                while True:
                    if args.coder_session_strategy == "always": teardown_coder_session(workdir)
                    print(f"State 3: Spawning Coder for {current_pr}")
                    dlog(f"Transitioning to State 3: Spawning Coder for {current_pr}")
                    notify_channel(effective_channel, f"Calling Coder for {base_filename}...", "coder_spawned", {"pr_id": base_filename})
                    try:
                        proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), "--pr-file", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--global-dir", global_dir, "--run-dir", job_dir_rel], start_new_session=True)
                        try:
                            proc.wait(timeout=MAX_RUNTIME)
                        except subprocess.TimeoutExpired:
                            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                            raise
                        class _CoderRes: pass # Reaper safety check: process already reaped or pgid not found
                        coder_result = _CoderRes()
                        coder_result.returncode = proc.returncode
                        if coder_result.returncode != 0:
                            state_5_trigger = True
                            break
                    except subprocess.TimeoutExpired:
                        state_5_trigger = True
                        break
                    status_output = drun(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
                    if status_output.strip(): dlog(f"Dirty status detected: {repr(status_output)}")
                    if status_output.strip():
                        coder_state_file = os.path.join(workdir, ".coder_state.json")
                        dirty_acknowledged = False
                        if os.path.exists(coder_state_file):
                            try:
                                import json
                                with open(coder_state_file, "r") as f:
                                    state_data = json.load(f)
                                    if state_data.get("dirty_acknowledged") is True: dirty_acknowledged = True
                            except Exception: pass # Reaper safety check: process already reaped or pgid not found
                        if not dirty_acknowledged:
                            try:
                                proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), "--pr-file", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--system-alert", status_output.strip(), "--global-dir", global_dir, "--run-dir", job_dir_rel], start_new_session=True)
                                try:
                                    proc.wait(timeout=MAX_RUNTIME)
                                except subprocess.TimeoutExpired:
                                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                                    raise
                                class _CoderRes: pass # Reaper safety check: process already reaped or pgid not found
                                coder_result = _CoderRes()
                                coder_result.returncode = proc.returncode
                                if coder_result.returncode != 0:
                                    state_5_trigger = True
                                    break
                            except subprocess.TimeoutExpired:
                                state_5_trigger = True
                                break
                            continue
                    review_artifact = os.path.join(job_dir_rel, "Review_Report.md")
                    review_report_path = os.path.join(workdir, review_artifact)
                    if os.path.exists(review_report_path): os.remove(review_report_path)
                    print(f"State 4: Spawning Reviewer for {current_pr}")
                    dlog(f"Transitioning to State 4: Spawning Reviewer for {current_pr}")
                    notify_channel(effective_channel, f"Coder submitted changes for {base_filename} ".strip() + f". Reviewer is now auditing...", "reviewer_spawned", {"pr_id": base_filename})
                    proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_reviewer.py"), "--pr-file", current_pr, "--diff-target", "master", "--workdir", workdir, "--global-dir", global_dir, "--out-file", review_artifact, "--run-dir", job_dir_rel], start_new_session=True)
                    proc.wait()
                    if os.path.exists(review_report_path):
                        with open(review_report_path, 'r', encoding='utf-8') as f: review_content = f.read()
                    else: review_content = ""
                
                    # New Structured JSON Parsing logic
                    verdict = parse_review_verdict(review_content)
                    if verdict == "APPROVED":
                        drun(["git", "reset", "--hard", "HEAD"])
                        drun(["git", "clean", "-fd"])
                        safe_git_checkout("master")
                        merge_result = drun([sys.executable, os.path.join(RUNTIME_DIR, "merge_code.py"), "--branch", branch_name, "--review-file", review_report_path])
                        if merge_result.returncode == 0:
                            drun(["git", "branch", "-D", branch_name], check=True)
                            set_pr_status(current_pr, "closed")
                            notify_channel(effective_channel, f"✅ {base_filename} successfully merged to master.", "pr_merged", {"pr_id": base_filename})
                            trigger_github_sync(workdir, effective_channel, base_filename)
                            teardown_coder_session(workdir)
                            pr_done = True
                            break
                        else:
                            state_5_trigger = True
                            break
                    elif verdict == "ACTION_REQUIRED" or "[ACTION_REQUIRED]" in review_content:
                        rejection_count += 1
                        notify_channel(effective_channel, "Reviewer rejected changes. Retrying...", "review_rejected", {"pr_id": base_filename, "summary": "Review reported ACTION_REQUIRED"})
                        if rejection_count < 5:
                            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), "--pr-file", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--feedback-file", review_report_path, "--global-dir", global_dir, "--run-dir", job_dir_rel], start_new_session=True)
                            proc.wait()
                            continue
                        else:
                            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_arbitrator.py"), "--pr-file", current_pr, "--diff-target", "master", "--workdir", workdir, "--run-dir", job_dir_rel], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            out, err = proc.communicate()
                            class _ArbRes: pass # Reaper safety check: process already reaped or pgid not found
                            arbitrator_result = _ArbRes()
                            arbitrator_result.stdout = out
                            if "[OVERRIDE_LGTM]" in arbitrator_result.stdout:
                                drun(["git", "reset", "--hard", "HEAD"])
                                drun(["git", "clean", "-fd"])
                                safe_git_checkout("master")
                                merge_result = drun([sys.executable, os.path.join(RUNTIME_DIR, "merge_code.py"), "--branch", branch_name, "--review-file", review_report_path])
                                if merge_result.returncode == 0:
                                    drun(["git", "branch", "-D", branch_name], check=True)
                                    set_pr_status(current_pr, "closed")
                                    notify_channel(effective_channel, f"✅ {base_filename} successfully merged to master.", "pr_merged", {"pr_id": base_filename})
                                    trigger_github_sync(workdir, effective_channel, base_filename)
                                    teardown_coder_session(workdir)
                                    pr_done = True
                                    break
                                else:
                                    state_5_trigger = True
                                    break
                            else:
                                state_5_trigger = True
                                break
                    else:
                        state_5_trigger = True
                        break
                if state_5_trigger:
                    if args.coder_session_strategy == "on-escalation": teardown_coder_session(workdir)

                    # PRD 1060: Forensic Quarantine: Use shutil.copytree instead of git tracking
                    job_dir_abs = os.path.join(workdir, job_dir_rel)
                    if os.path.exists(job_dir_abs):
                        import shutil
                        timestamp = int(time.time())
                        crashed_dir = f"{job_dir_abs}_crashed_{timestamp}"
                        print(f"State 5: Archiving forensic artifacts to snapshot: {crashed_dir}")
                        dlog(f"Transitioning to State 5: Archiving crashed dir to {crashed_dir}")
                        try:
                            shutil.copytree(job_dir_abs, crashed_dir, dirs_exist_ok=True)
                        except FileNotFoundError:
                            pass

                    if reset_count == 0:
                        print(f"State 5 Escalation - Tier 1 (Reset): Deleting branch and retrying.")
                        dlog(f"State 5 Escalation: Tier 1 reset triggered. Resetting {branch_name}")
                        drun(["git", "reset", "--hard"], check=False)
                        drun(["git", "clean", "-fd"], check=False)
                        safe_git_checkout("master")
                        drun(["git", "branch", "-D", branch_name], check=False)
                        
                        reset_count += 1
                        continue
                    else:
                        drun(["git", "checkout", "master"], check=False)
                        
                        # In test mode, we might delete the file or branch. Just skip the slice if we can't find it.
                        if not os.path.exists(current_pr):
                            print(f"[Warning] PR file {current_pr} not found after state 5 reset. Aborting slice.")
                            print(HandoffPrompter.get_prompt("dead_end"))
                            sys.exit(1)
                            
                        slice_depth = get_pr_slice_depth(current_pr)
                        if slice_depth < 2:
                            pr_files_before = set(glob.glob(os.path.join(job_dir, "PR_*.md")))
                            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--slice-failed-pr", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--global-dir", global_dir], start_new_session=True)
                            proc.wait()
                            pr_files_after = set(glob.glob(os.path.join(job_dir, "PR_*.md")))
                            new_files = pr_files_after - pr_files_before
                            if len(new_files) >= 2:
                                set_pr_status(current_pr, "superseded")
                                pr_done = True
                                break
                            else:
                                set_pr_status(current_pr, "blocked_fatal")
                                print(HandoffPrompter.get_prompt("dead_end"))
                                sys.exit(1)
                        else:
                            set_pr_status(current_pr, "blocked_fatal")
                            print(HandoffPrompter.get_prompt("dead_end"))
                            sys.exit(1)


    except KeyboardInterrupt:
        print(HandoffPrompter.get_prompt("fatal_interrupt"))
        raise
    except SystemExit as e:
        raise
    except Exception as e:
        traceback.print_exc()
        print(HandoffPrompter.get_prompt("fatal_crash"))
        raise
    finally:
        if 'proc' in locals() and proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except OSError:
                pass # Reaper safety check: process already reaped or pgid not found

if __name__ == "__main__":
    main()
