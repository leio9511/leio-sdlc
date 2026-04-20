#!/usr/bin/env python3
import os
import sys
from agent_driver import invoke_agent, build_prompt, notify_channel
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
from git_utils import safe_git_checkout, GitCheckoutError, get_mainline_branch
from notification_formatter import format_notification
from handoff_prompter import HandoffPrompter
from utils_json import extract_and_parse_json

MAX_RUNTIME = int(os.environ.get("SDLC_TIMEOUT", 3600)) # 60 minutes default

import json
import config

def load_or_merge_config(sdlc_root):
    template_path = os.path.join(sdlc_root, "config", "sdlc_config.json.template")
    config_path = os.path.join(sdlc_root, "config", "sdlc_config.json")
    
    config_template = {}
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            config_template = json.load(f)
            
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                local_config = json.load(f)
            except json.JSONDecodeError:
                local_config = {}
        changed = False
        for k, v in config_template.items():
            if k not in local_config:
                local_config[k] = v
                changed = True
        if changed and os.environ.get("SDLC_TEST_MODE") != "true":
            # PR-002: Prevent physical config write if in test mode
            with open(config_path, "w") as fw:
                json.dump(local_config, fw, indent=4)
        return local_config
    else:
        if os.environ.get("SDLC_TEST_MODE") != "true":
            # PR-002: Prevent physical config write if in test mode
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(config_template, f, indent=4)
        return config_template

def dlog(msg):
    import logging
    logger = logging.getLogger("sdlc_orchestrator")
    logger.debug(msg)

def drun(cmd, **kwargs):
    import logging
    logger = logging.getLogger("sdlc_orchestrator")
    logger.debug(f"DEBUG [Subprocess]: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, **kwargs)
    logger.debug(f"DEBUG [Subprocess Return]: {res.returncode}")
    if hasattr(res, 'stdout') and isinstance(res.stdout, str) and res.stdout.strip():
        logger.debug(f"DEBUG [Subprocess Stdout]: {res.stdout.strip()}")
    if hasattr(res, 'stderr') and isinstance(res.stderr, str) and res.stderr.strip():
        logger.debug(f"DEBUG [Subprocess Stderr]: {res.stderr.strip()}")
    return res

def dpopen(cmd, **kwargs):
    import logging
    logger = logging.getLogger("sdlc_orchestrator")
    logger.debug(f"DEBUG [Subprocess Popen]: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return subprocess.Popen(cmd, **kwargs)


import hashlib

def assign_gemini_api_key(session_key, gemini_api_keys, state_file_path):
    if not gemini_api_keys:
        return None
        
    os.makedirs(os.path.dirname(state_file_path), exist_ok=True)
    try:
        fd = os.open(state_file_path, os.O_CREAT | os.O_RDWR)
    except Exception:
        # Graceful degradation if file cannot be opened
        return None
        
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        
        state = {}
        try:
            file_size = os.fstat(fd).st_size
            if file_size > 0:
                os.lseek(fd, 0, os.SEEK_SET)
                content = os.read(fd, file_size).decode('utf-8')
                state = json.loads(content)
        except Exception:
            pass
            
        fingerprint = state.get(session_key)
        
        if fingerprint:
            for key in gemini_api_keys:
                if key.endswith(fingerprint):
                    return key
                    
        idx = int(hashlib.md5(session_key.encode("utf-8")).hexdigest(), 16) % len(gemini_api_keys)
        selected_key = gemini_api_keys[idx]
        new_fingerprint = selected_key[-8:] if len(selected_key) >= 8 else selected_key
        
        state[session_key] = new_fingerprint
        
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps(state, indent=2).encode('utf-8'))
        
        return selected_key
        
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

def get_env_with_gemini_key(session_key, gemini_api_keys, global_dir):
    env = os.environ.copy()
    if not gemini_api_keys:
        return env
        
    state_file_path = os.path.join(global_dir, ".sdlc_runs", ".session_keys.json")
    assigned_key = assign_gemini_api_key(session_key, gemini_api_keys, state_file_path)
    if assigned_key:
        env["GEMINI_API_KEY"] = assigned_key
    return env

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

import tempfile

def acquire_global_locks(projects, workdir):
    lock_dir = os.path.join(tempfile.gettempdir(), "openclaw_locks")
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

from structured_state_parser import update_status as _update_status

def set_pr_status(pr_file, new_status):
    _update_status(pr_file, new_status)
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

def teardown_coder_session(workdir, run_dir="."):
    session_file = os.path.join(run_dir, ".coder_session")
    if os.path.exists(session_file):
        with open(session_file, "r") as f:
            session_key = f.read().strip()
        if session_key:
            print(f"Tearing down coder session {session_key}")
        try:
            os.remove(session_file)
        except OSError:
            pass # Reaper safety check: process already reaped or pgid not found

def validate_prd_is_committed(prd_file, workdir):
    prd_path_abs = os.path.abspath(prd_file)
    if os.path.exists(prd_path_abs):
        try:
            drun(["git", "ls-files", "--error-unmatch", prd_path_abs], check=True, capture_output=True, cwd=workdir)
        except subprocess.CalledProcessError:
            print(f"[FATAL] Workspace contains uncommitted state files. You MUST baseline your PRD and state using the official gateway: python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py --files <path>")
            print('[JIT] To fix: Ensure your PRD path is within the Git repository boundaries.\nIf it is, use the official gateway script (commit_state.py) from the active SDLC runtime to baseline it.')
            sys.exit(1)

        status_out = drun(["git", "status", "--porcelain", prd_path_abs], capture_output=True, text=True, cwd=workdir).stdout.strip()
        if status_out:
            print(f"[FATAL] Workspace contains uncommitted state files. You MUST baseline your PRD and state using the official gateway: python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/commit_state.py --files <path>")
            print('[JIT] To fix: Ensure your PRD path is within the Git repository boundaries.\nIf it is, use the official gateway script (commit_state.py) from the active SDLC runtime to baseline it.')
            sys.exit(1)

from utils_json import extract_and_parse_json

def parse_review_verdict(content):
    """
    Parses structured JSON review status using the new schema.
    """
    try:
        data = extract_and_parse_json(content)
        if data and isinstance(data, dict):
            assessment = data.get("overall_assessment")
            if assessment in ["EXCELLENT", "GOOD_WITH_MINOR_SUGGESTIONS"]:
                return "APPROVED"
            elif assessment in ["NEEDS_ATTENTION", "NEEDS_IMMEDIATE_REWORK"]:
                return "ACTION_REQUIRED"
    except Exception:
        pass
    return None




class SanityContext:
    def __init__(self, workdir, job_dir, base_name, force_replan):
        self.workdir = workdir
        self.job_dir = job_dir
        self.base_name = base_name
        self.force_replan = force_replan

    def perform_healthy_check(self):
        if self.force_replan != "false":
            return

        import os, sys, subprocess
        baseline_file = os.path.join(self.job_dir, "baseline_commit.txt")
        if not os.path.exists(self.job_dir) or not os.path.exists(baseline_file):
            print("Handoff_Metadata_Missing: [FATAL_METADATA] Critical SDLC anchors (baseline_commit.txt) are missing. Automatic recovery is impossible. You must manually verify the repository state or use --force-replan true.")
            sys.exit(1)

        res = subprocess.run(["git", "branch", "--show-current"], cwd=self.workdir, capture_output=True, text=True)
        current_branch = res.stdout.strip()
        if current_branch and current_branch not in ["master", "main"]:
            if not current_branch.startswith(f"{self.base_name}/"):
                print(f"[FATAL_METADATA] Current branch '{current_branch}' does not match PRD naming convention '{self.base_name}/'.")
                sys.exit(1)

        with open(baseline_file, "r") as f:
            baseline_hash = f.read().strip()

        res = subprocess.run(["git", "merge-base", "--is-ancestor", baseline_hash, "HEAD"], cwd=self.workdir)
        if res.returncode != 0:
            print("[FATAL_METADATA] Current Git HEAD is not reachable from the baseline hash.")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--prd-file", required=True)
    parser.add_argument("--max-prs-to-process", type=int, default=50)
    parser.add_argument("--coder-session-strategy", default="on-escalation", choices=["always", "per-pr", "on-escalation"])
    parser.add_argument("--force-replan", choices=["true", "false"], default=None, help="只有明确的知道是要继续同一个prd的执行，保留原有的pr，继续完成未完成的pr，才把force-replan设成false。如果明确的是要重新执行一个prd，比如在prd更新之后，或者在prd的sdlc执行已经被明确的完全revert之后，就应该把force-replan设成true。如果不确定应该是true还是false，应该停下来征求boss的意见。")
    parser.add_argument("--channel", help="Notification channel")
    parser.add_argument("--global-dir", help="Global workspace path")
    parser.add_argument("--test-sleep", action="store_true")
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass # Reaper safety check: process already reaped or pgid not found the workspace path check")

    parser.add_argument("--cleanup", action="store_true", help="Lock-aware forensic quarantine of crashed orchestrator state")
    parser.add_argument("--resume", action="store_true", help="Checkpoint-based Task Restart. Use this flag if the SDLC was interrupted and you need to resume or continue from the last successful checkpoint.")
    parser.add_argument("--withdraw", action="store_true", help="Atomic State Restoration and Withdrawal. Use this flag if the user's intent is to 'withdraw', 'rollback', or 'cancel' the entire PRD execution.")
    parser.add_argument("--debug", action="store_true", help="Enable debug trace logs")
    parser.add_argument("--engine", choices=["openclaw", "gemini"], default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE), help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})")
    parser.add_argument("--model", default=os.environ.get("SDLC_MODEL", config.DEFAULT_GEMINI_MODEL), help=f"Model to use when --engine is gemini (default: {config.DEFAULT_GEMINI_MODEL})")
    args = parser.parse_args()
    
    if isinstance(args.engine, str) and args.engine != os.environ.get("LLM_DRIVER"):
        os.environ["LLM_DRIVER"] = args.engine
    if isinstance(args.model, str) and args.model != os.environ.get("SDLC_MODEL"):
        os.environ["SDLC_MODEL"] = args.model

    execution_log_msg = f"Orchestrator Engine Configured -> Engine: {args.engine}, Model: {args.model}"
    print(execution_log_msg)

    # Store debug mode in the application's configuration state
    os.environ["SDLC_DEBUG_MODE"] = "1" if args.debug else "0"

    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    sdlc_root = os.path.dirname(RUNTIME_DIR)
    app_config = load_or_merge_config(sdlc_root)
    gemini_api_keys = app_config.get('gemini_api_keys', [])
    
    resolved_global_dir = None
    if args.global_dir:
        resolved_global_dir = os.path.abspath(args.global_dir)
    elif app_config.get("GLOBAL_RUN_DIR"):
        resolved_global_dir = os.path.abspath(app_config.get("GLOBAL_RUN_DIR"))
        
    global_dir = resolved_global_dir if resolved_global_dir else os.path.abspath(args.workdir)


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
            run_dir = os.path.join(global_dir, '.sdlc_runs', parent_dir_name)

        if branch_output in ["master", "main"]:
            print("Cannot quarantine master/main branch.")
            sys.exit(1)
            
        drun(["git", "add", "-A"], check=False)
        drun(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
        timestamp = int(time.time())
        drun(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
        drun(["git", "checkout", get_mainline_branch(args.workdir)], check=False)
        
        # 8. Targeted Artifact Obliteration (os.remove for daemon locks)
        for lockfile in [".coder_session", ".sdlc_repo.lock"]:
            try:
                os.remove(os.path.join(args.workdir, lockfile))
            except OSError:
                pass # Already deleted
        
        manifest_path = os.path.join(args.workdir, ".sdlc_lock_manifest.json")
        if os.path.exists(manifest_path):
            try:
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

    if getattr(args, "withdraw", False) is True:
        lock_path = os.path.join(args.workdir, ".sdlc_repo.lock")
        try:
            f_lock = open(lock_path, "w")
            fcntl.flock(f_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError):
            print("[FATAL_LOCK] Cannot clean up while another SDLC pipeline is active.")
            sys.exit(1)

        os.chdir(args.workdir)
        branch_res = drun(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch_output = branch_res.stdout.strip()

        prd_filename = os.path.basename(args.prd_file)
        base_name, _ = os.path.splitext(prd_filename)
        target_project_name = os.path.basename(os.path.abspath(args.workdir))
        job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
        
        withdrawn_dir = f"{job_dir}.withdrawn"
        if os.path.exists(withdrawn_dir) and not os.path.exists(job_dir):
            print(f"[INFO] PRD {base_name} has already been withdrawn. Ignoring.")
            sys.exit(0)

        baseline_file = os.path.join(job_dir, "baseline_commit.txt")
        if not os.path.exists(job_dir) or not os.path.exists(baseline_file):
            print("Handoff_Metadata_Missing: [FATAL_METADATA] Critical SDLC anchors (baseline_commit.txt) are missing. Automatic recovery is impossible. You must manually verify the repository state or use --force-replan true.")
            sys.exit(1)

        with open(baseline_file, "r") as f:
            baseline_hash = f.read().strip()

        log_res = drun(["git", "log", f"{baseline_hash}..HEAD", "--oneline"], capture_output=True, text=True)
        if log_res.stdout.strip():
            print("[WARNING] Unauthorized external commits detected between baseline and HEAD. These changes are NOT protected by SDLC and will be overwritten to ensure baseline integrity.")

        if branch_output in ["master", "main"]:
            drun(["git", "stash", "push", "-m", "SDLC Withdrawal Emergency Stash"], check=False)
        else:
            drun(["git", "add", "-A"], check=False)
            drun(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
            timestamp = int(time.time())
            drun(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
            drun(["git", "checkout", get_mainline_branch(args.workdir)], check=False)

        interrupted_hash_res = drun(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
        interrupted_hash = interrupted_hash_res.stdout.strip()

        drun(["git", "reset", "--hard", baseline_hash], check=True)
        drun(["git", "reset", "--soft", interrupted_hash], check=True)
        
        diff_check = drun(["git", "diff", "--cached", "--quiet"])
        if diff_check.returncode != 0:
            commit_msg = f"chore: force baseline alignment of PRD {base_name} to baseline"
            drun(["git", "commit", "-m", commit_msg], check=True)

        withdrawn_dir = f"{job_dir}.withdrawn"
        if os.path.exists(job_dir):
            import shutil
            shutil.move(job_dir, withdrawn_dir)

        manifest_path = os.path.join(args.workdir, ".sdlc_lock_manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    manifest_data = json.load(f)
                for lock_path in manifest_data.get("locks", []):
                    try:
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                    except OSError:
                        pass
                os.remove(manifest_path)
            except Exception:
                pass
                
        for lockfile in [".coder_session", ".sdlc_repo.lock"]:
            try:
                os.remove(os.path.join(args.workdir, lockfile))
            except OSError:
                pass

        sys.exit(0)

    if not args.test_sleep and getattr(args, "force_replan", None) is None and not getattr(args, "resume", False) and not getattr(args, "withdraw", False):
        print("[FATAL] Missing required parameter: --force-replan must be either 'true' or 'false'.")
        print(HandoffPrompter.get_prompt("startup_validation_failed"))
        sys.exit(1)

    if getattr(args, "force_replan", None) is not None:
        args.force_replan = str(args.force_replan).lower()

    # SDLC_TEST_MODE Leakage Guardrail
    if os.environ.get("SDLC_TEST_MODE") == "true":
        if args.enable_exec_from_workspace:
            print("[WARNING] Running Orchestrator in TEST MODE with mocked LLMs. Production safety checks are bypassed.")
        else:
            print(HandoffPrompter.get_prompt("test_mode_leakage"))
            sys.exit(1)

    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    workdir = os.path.abspath(args.workdir)
    import logging
    from setup_logging import setup_orchestrator_logger
    logger = setup_orchestrator_logger(workdir, args.debug)
    dlog(f"Workdir: {workdir}")
    
    # 1. Blast Radius Control: Scan and delete all .coder_session files using glob
    dlog("Executing Blast Radius Control...")
    import glob
    for session_file_path in glob.glob(os.path.join(workdir, "**", ".coder_session"), recursive=True):
        try:
            os.remove(session_file_path)
            dlog(f"Blast Radius Control: Removed {session_file_path}")
        except OSError as e:
            dlog(f"Blast Radius Control: Failed to remove {session_file_path}: {e}")
                
    from git_utils import check_git_boundary
    check_git_boundary(workdir)

    doctor_script = os.path.join(RUNTIME_DIR, "doctor.py")
    if os.path.exists(doctor_script):
        dlog("Running SDLC Doctor check...")
        res = drun([sys.executable, doctor_script, workdir, "--check"], capture_output=True, text=True)
        if res.returncode != 0:
            print(f'[FATAL] Project is not SDLC compliant. Please run "python3 {config.SDLC_SKILLS_ROOT}/leio-sdlc/scripts/doctor.py --fix" to apply the required infrastructure.')
            print(HandoffPrompter.get_prompt("startup_validation_failed"))
            sys.exit(1)

    os.chdir(workdir)

    if getattr(args, "resume", False):
        from structured_state_parser import get_status, update_status
        
        prd_filename = os.path.basename(args.prd_file)
        base_name, _ = os.path.splitext(prd_filename)
        target_project_name = os.path.basename(os.path.abspath(workdir))
        resume_job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
        
        if os.path.exists(resume_job_dir):
            for pr_file in glob.glob(os.path.join(resume_job_dir, "PR_*.md")):
                try:
                    if get_status(pr_file) == "in_progress":
                        update_status(pr_file, "open")
                except ValueError:
                    pass
                    
        status_output = drun(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
        if status_output.strip():
            branch_output = drun(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
            if branch_output in ["master", "main"]:
                drun(["git", "stash", "push", "-m", "SDLC Withdrawal Emergency Stash"], check=False)
            else:
                drun(["git", "add", "-A"], check=False)
                drun(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
                timestamp = int(time.time())
                drun(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
                drun(["git", "checkout", get_mainline_branch(workdir)], check=False)
                
        args.force_replan = "false"

    validate_prd_is_committed(args.prd_file, workdir)
    dlog("Checking branch guardrail...")
    if os.environ.get("SDLC_BYPASS_BRANCH_CHECK") != "1":
        if not os.path.exists(".git"):
            print("[FATAL] Git Boundary Enforcement: workdir must contain a .git directory.")
            print(HandoffPrompter.get_prompt("invalid_git_boundary"))
            sys.exit(1)
        
        branch_output = drun(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        force_replan_val = getattr(args, "force_replan", "false")
        
        if force_replan_val != "false":
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
        print('[JIT] To fix: Execute `git stash push -m "sdlc pre-flight stash" --include-untracked` to safely preserve state.')
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
    target_project_name = os.path.basename(os.path.abspath(workdir))
    job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
    run_dir = job_dir

    sanity = SanityContext(workdir, job_dir, base_name, getattr(args, "force_replan", "false"))
    sanity.perform_healthy_check()

    if os.path.exists(job_dir) and args.force_replan == "false":
        md_files = glob.glob(os.path.join(job_dir, "*.md"))
        if len(md_files) > 0 and not os.path.exists(os.path.join(job_dir, ".queue_empty_force")):
            import shlex
            full_cmd = shlex.join([sys.executable] + sys.argv)
            logger.info("State 0: Existing PRs detected. Resuming queue...")
            dlog(f"Transitioning to State 0 for PRD {prd_filename} (resuming)")
            notify_channel(effective_channel, "Ignition: Resuming existing queue...", "sdlc_resume", {"prd_id": prd_filename, "command": full_cmd})
        elif os.path.exists(os.path.join(job_dir, ".queue_empty_force")):
            pass
        else:
            if args.force_replan == "true" and os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir)
            import shlex
            full_cmd = shlex.join([sys.executable] + sys.argv)
            logger.info("State 0: Auto-slicing PRD...")
            dlog(f"Transitioning to State 0 for PRD {prd_filename} (auto-slicing)")
            notify_channel(effective_channel, "Ignition: Starting new SDLC pipeline...", "sdlc_start", {"prd_id": prd_filename, "command": full_cmd})
            notify_channel(effective_channel, "State 0: Auto-slicing PRD...", "slicing_start", {"prd_id": prd_filename})
            try:
                proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--prd-file", args.prd_file, "--workdir", workdir, "--global-dir", global_dir, "--run-dir", run_dir], start_new_session=True, env=get_env_with_gemini_key(f"{base_name}_planner", gemini_api_keys, global_dir))
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
    else:
        if args.force_replan == "true" and os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir)
        import shlex
        full_cmd = shlex.join([sys.executable] + sys.argv)
        logger.info("State 0: Auto-slicing PRD...")
        dlog(f"Transitioning to State 0 for PRD {prd_filename} (auto-slicing)")
        notify_channel(effective_channel, "Ignition: Starting new SDLC pipeline...", "sdlc_start", {"prd_id": prd_filename, "command": full_cmd})
        notify_channel(effective_channel, "State 0: Auto-slicing PRD...", "slicing_start", {"prd_id": prd_filename})
        try:
            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--prd-file", args.prd_file, "--workdir", workdir, "--global-dir", global_dir, "--run-dir", run_dir], start_new_session=True, env=get_env_with_gemini_key(f"{base_name}_planner", gemini_api_keys, global_dir))
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


    # Record baseline commit before starting the main loop
    os.makedirs(job_dir, exist_ok=True)
    baseline_file = os.path.join(job_dir, "baseline_commit.txt")
    if not os.path.exists(baseline_file):
        try:
            head_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True, text=True, check=True)
            baseline_hash = head_res.stdout.strip()
            with open(baseline_file, "w") as f:
                f.write(baseline_hash)
            logger.info(f"Recorded baseline commit: {baseline_hash}")
        except Exception as e:
            logger.warning(f"Failed to record baseline commit: {e}")

    proc = None

    def sig_handler(signum, frame):
        print(HandoffPrompter.get_prompt("fatal_interrupt"))
        raise SystemExit(1)
    
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    try:
        loops = 0
        
        # Load Retry Config
        yellow_retry_limit = 3
        red_retry_limit = 2
        config_path = os.path.join(global_dir, "config", "sdlc_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    app_config_data = json.load(f)
                    yellow_retry_limit = app_config_data.get("YELLOW_RETRY_LIMIT", 3)
                    red_retry_limit = app_config_data.get("RED_RETRY_LIMIT", 2)
            except Exception:
                pass
                
        while True:
            if args.max_prs_to_process > 0 and loops >= args.max_prs_to_process:
                print(f"Max runs reached. Exiting orchestrator.")
                break
            loops += 1
            md_files = glob.glob(os.path.join(job_dir, "*.md"))
            md_files.sort()
            current_pr = None
            logger.debug(f"Scanning job_dir: {job_dir}")
            logger.debug(f"Found md_files: {md_files}")
            for md_file in md_files:
                with open(md_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                    first_50 = file_content[:50].replace('\n', '\\n')
                    match = re.search(r'^status:\s*in_progress', file_content, re.MULTILINE)
                    logger.debug(f"Scanning {md_file}: start='{first_50}', in_progress={bool(match)}")
                    if match:
                        current_pr = md_file
                        break
            if not current_pr:
                result = drun([sys.executable, os.path.join(RUNTIME_DIR, "get_next_pr.py"), "--workdir", workdir, "--job-dir", job_dir], capture_output=True, text=True)
                output = result.stdout.strip()
                logger.debug(f"get_next_pr.py exit_code={result.returncode}, output='{output}'")
                if "[QUEUE_EMPTY]" in output or not output:
                    logger.info("State 6: UAT Verification")
                    prd_files_set = {os.path.abspath(args.prd_file)}
                    for f in glob.glob(os.path.join(job_dir, "PRD_*.md")):
                        prd_files_set.add(os.path.abspath(f))
                    prd_files_str = ",".join(list(prd_files_set))
                    
                    uat_out_file = os.path.abspath(os.path.join(run_dir, "uat_report.json"))
                    if os.path.exists(uat_out_file):
                        try:
                            os.remove(uat_out_file)
                        except OSError:
                            pass
                    
                    uat_cmd = [
                        sys.executable, os.path.join(RUNTIME_DIR, "spawn_verifier.py"),
                        "--prd-files", prd_files_str,
                        "--workdir", workdir,
                        "--out-file", uat_out_file
                    ]
                    if args.enable_exec_from_workspace:
                        uat_cmd.append("--enable-exec-from-workspace")
                        
                    res = drun(uat_cmd, capture_output=True, text=True, env=get_env_with_gemini_key(f"{base_name}_verifier", gemini_api_keys, global_dir))
                    if hasattr(args, "debug") and args.debug:
                        logger.debug(f"UAT Verifier returned {res.returncode}. Output:\n{res.stdout}\n{res.stderr}")

                    
                    uat_status = "UNKNOWN"
                    if os.path.exists(uat_out_file):
                        try:
                            with open(uat_out_file, "r") as f:
                                uat_data = json.load(f)
                                uat_status = uat_data.get("status", "UNKNOWN")
                        except Exception as e:
                            dlog(f"Failed to parse uat_report.json: {e}")
                            
                    if uat_status not in ["PASS", "NEEDS_FIX"]:
                        print("[ACTION REQUIRED FOR MANAGER] UAT Failed. uat_report.json is missing or invalid JSON.")
                        notify_channel(effective_channel, "UAT Verification failed due to missing or invalid JSON report. Manager is reviewing...", "uat_error", {"prd_id": prd_filename})
                        sys.exit(1)
                        
                    msg = f"UAT Verification completed. Status: {uat_status}. Manager is reviewing..."
                    notify_channel(effective_channel, msg, "uat_complete", {"prd_id": prd_filename, "status": uat_status})
                    
                    if uat_status == "PASS":
                        print("[SUCCESS_HANDOFF] UAT Passed. You are authorized to close the ticket using issues.py.")
                        sys.exit(0)
                    else:
                        print("[ACTION REQUIRED FOR MANAGER] UAT Failed. Read uat_report.json, summarize the MISSING items to the Boss, and ask whether to append a hotfix or redo.")
                        sys.exit(1)

                current_pr = output.split('\n')[-1].strip()
                if not os.path.exists(current_pr):
                    print(HandoffPrompter.get_prompt("dead_end"))
                    sys.exit(1)
                set_pr_status(current_pr, "in_progress")

            if args.coder_session_strategy == "per-pr": teardown_coder_session(workdir, run_dir)
            base_filename = os.path.splitext(os.path.basename(current_pr))[0]
            parent_dir_name = os.path.basename(os.path.dirname(os.path.abspath(current_pr)))
            branch_name = f"{parent_dir_name}/{base_filename}".replace(":", "_").replace(" ", "_").replace("?", "_")
            pr_done = False
            # Reset Resilience Counters per PR for Red Path logic
            red_counter = 0

            while True:
                if pr_done: break
                logger.info(f"State 2: Checking out branch {branch_name}")
                dlog(f"Transitioning to State 2: Checkout branch {branch_name} for PR {current_pr}")
                try:
                    branch_check = drun(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"])
                    if branch_check.returncode == 0: safe_git_checkout(branch_name)
                    else: safe_git_checkout(branch_name, create=True)
                except GitCheckoutError as e:
                    print(HandoffPrompter.get_prompt("git_checkout_error"))
                    sys.exit(1)
                
                # State Machine Expansion: initialize retry counters
                yellow_counter = 0
                orch_yellow_counter = 0
                state_5_trigger = False
                current_feedback_file = None
                system_alert_text = None
                while True:
                    if args.coder_session_strategy == "always": teardown_coder_session(workdir, run_dir)
                    logger.info(f"State 3: Spawning Coder for {current_pr}")
                    dlog(f"Transitioning to State 3: Spawning Coder for {current_pr}")
                    notify_channel(effective_channel, f"Calling Coder for {base_filename}...", "coder_spawned", {"pr_id": base_filename})
                    
                    coder_cmd = [sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), "--pr-file", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--global-dir", global_dir, "--run-dir", run_dir]
                    if current_feedback_file:
                        coder_cmd.extend(["--feedback-file", current_feedback_file])
                    if system_alert_text:
                        coder_cmd.extend(["--system-alert", system_alert_text])
                        system_alert_text = None
                        
                    proc = dpopen(coder_cmd, start_new_session=True, env=get_env_with_gemini_key(f"{base_filename}_coder", gemini_api_keys, global_dir))
                    try:
                        proc.wait(timeout=MAX_RUNTIME)
                    except subprocess.TimeoutExpired:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                            proc.wait()
                        state_5_trigger = True
                        break
                    class _CoderRes: pass # Reaper safety check: process already reaped or pgid not found
                    coder_result = _CoderRes()
                    coder_result.returncode = proc.returncode
                    if coder_result.returncode != 0:
                        state_5_trigger = True
                        break

                    status_output = drun(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
                    if status_output.strip():
                        dlog(f"Dirty status detected: {repr(status_output)}")
                        orch_yellow_counter += 1
                        if orch_yellow_counter >= yellow_retry_limit:
                            state_5_trigger = True
                            break
                        system_alert_text = status_output.strip()
                        continue
                    
                    preflight_script = os.path.join(workdir, "preflight.sh")
                    if os.path.exists(preflight_script):
                        res = drun([preflight_script], capture_output=True, text=True, cwd=workdir)
                        if res.returncode != 0:
                            dlog(f"Preflight failed with code {res.returncode}")
                            orch_yellow_counter += 1
                            if orch_yellow_counter >= yellow_retry_limit:
                                state_5_trigger = True
                                break
                            system_alert_text = f"Preflight failed:\n{res.stdout}\n{res.stderr}".strip()
                            continue

                    orch_yellow_counter = 0
                    
                    review_artifact = os.path.join(run_dir, "review_report.json")
                    review_report_path = os.path.join(workdir, review_artifact)
                    if os.path.exists(review_report_path): os.remove(review_report_path)
                    logger.info(f"State 4: Spawning Reviewer for {current_pr}")
                    dlog(f"Transitioning to State 4: Spawning Reviewer for {current_pr}")
                    notify_channel(effective_channel, f"Coder submitted changes for {base_filename} ".strip() + f". Reviewer is now auditing...", "reviewer_spawned", {"pr_id": base_filename})
                    proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_reviewer.py"), "--prd-file", args.prd_file, "--pr-file", current_pr, "--diff-target", get_mainline_branch(workdir), "--workdir", workdir, "--global-dir", global_dir, "--out-file", review_artifact, "--run-dir", run_dir], start_new_session=True, env=get_env_with_gemini_key(f"{base_filename}_reviewer", gemini_api_keys, global_dir))
                    proc.wait()
                    
                    json_retry_count = 0
                    max_json_retries = 3
                    verdict = None
                    
                    while json_retry_count < max_json_retries:
                        if os.path.exists(review_report_path):
                            with open(review_report_path, 'r', encoding='utf-8') as f: review_content = f.read()
                        else: review_content = ""
                    
                        try:
                            # Use new robust parser
                            data = extract_and_parse_json(review_content)
                            assessment = data.get("overall_assessment") if isinstance(data, dict) else None
                            if assessment in ["EXCELLENT", "GOOD_WITH_MINOR_SUGGESTIONS"]:
                                verdict = "APPROVED"
                            elif assessment in ["NEEDS_ATTENTION", "NEEDS_IMMEDIATE_REWORK"]:
                                verdict = "ACTION_REQUIRED"
                            else:
                                verdict = None
                            break # successfully parsed, exit loop
                        except ValueError as e:
                            json_retry_count += 1
                            logger.warning(f"Failed to parse Reviewer JSON (Attempt {json_retry_count}/{max_json_retries}). Retrying with system alert.")
                            if json_retry_count >= max_json_retries:
                                break
                                
                            sys_alert = "SYSTEM ALERT: Your previous output could not be parsed as valid JSON. Please return ONLY a strict JSON object matching the required schema. No markdown formatting, no conversational text."
                            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_reviewer.py"), "--prd-file", args.prd_file, "--pr-file", current_pr, "--diff-target", get_mainline_branch(workdir), "--workdir", workdir, "--global-dir", global_dir, "--out-file", review_artifact, "--run-dir", run_dir, "--system-alert", sys_alert], start_new_session=True, env=get_env_with_gemini_key(f"{base_filename}_reviewer", gemini_api_keys, global_dir))
                            proc.wait()
                                
                    if verdict == "APPROVED":
                        drun(["git", "reset", "--hard", "HEAD"])
                        drun(["git", "clean", "-fd"])
                        safe_git_checkout(get_mainline_branch(workdir))
                        merge_result = drun([sys.executable, os.path.join(RUNTIME_DIR, "merge_code.py"), "--branch", branch_name, "--review-file", review_report_path])
                        if merge_result.returncode == 0:
                            drun(["git", "branch", "-D", branch_name], check=True)
                            set_pr_status(current_pr, "closed")
                            notify_channel(effective_channel, f"✅ {base_filename} successfully merged to master.", "pr_merged", {"pr_id": base_filename})
                            teardown_coder_session(workdir)
                            pr_done = True
                            break
                        else:
                            state_5_trigger = True
                            break
                    elif verdict == "ACTION_REQUIRED" or "[ACTION_REQUIRED]" in review_content:
                        # Yellow Path logic: Keep current session ID and increment counter
                        yellow_counter += 1
                        notify_channel(effective_channel, f"Reviewer rejected changes (Yellow Path: {yellow_counter}/{yellow_retry_limit}). Retrying...", "review_rejected", {"pr_id": base_filename, "summary": "Review reported ACTION_REQUIRED"})
                        if yellow_counter < yellow_retry_limit:
                            current_feedback_file = review_report_path
                            continue
                        else:
                            state_5_trigger = True
                            break
                    else:
                        state_5_trigger = True
                        break
                if state_5_trigger:
                    if args.coder_session_strategy == "on-escalation": teardown_coder_session(workdir, run_dir)

                    # PRD 1060: Forensic Quarantine: Use shutil.copytree instead of git tracking
                    job_dir_abs = run_dir
                    if os.path.exists(job_dir_abs):
                        import shutil
                        timestamp = int(time.time())
                        crashed_dir = f"{job_dir_abs}_crashed_{timestamp}"
                        logger.info(f"State 5: Archiving forensic artifacts to snapshot: {crashed_dir}")
                        dlog(f"Transitioning to State 5: Archiving crashed dir to {crashed_dir}")
                        try:
                            shutil.copytree(job_dir_abs, crashed_dir, dirs_exist_ok=True)
                        except FileNotFoundError:
                            pass

                    if red_counter < red_retry_limit:
                        print(f"State 5 Escalation - Tier 1 (Reset): Deleting branch and retrying.")
                        print(f"State 5 Escalation - Red Path Triggered: Hard Reset Session Cycling ({red_counter+1}/{red_retry_limit}).")
                        dlog(f"State 5 Escalation: Tier 1 reset triggered. Resetting {branch_name}")
                        dlog(f"State 5 Escalation: Red Path reset triggered. Resetting {branch_name}")
                        drun(["git", "reset", "--hard"], check=False)
                        drun(["git", "clean", "-fd"], check=False)
                        safe_git_checkout(get_mainline_branch(workdir))
                        drun(["git", "branch", "-D", branch_name], check=False)
                        
                        # RED PATH ENFORCEMENT: Force a NEW Session ID
                        teardown_coder_session(workdir, run_dir)
                        
                        red_counter += 1
                        continue
                    else:
                        drun(["git", "checkout", get_mainline_branch(workdir)], check=False)
                        
                        # In test mode, we might delete the file or branch. Just skip the slice if we can't find it.
                        if not os.path.exists(current_pr):
                            print(f"[Warning] PR file {current_pr} not found after state 5 reset. Aborting slice.")
                            print(HandoffPrompter.get_prompt("dead_end"))
                            sys.exit(1)
                            
                        slice_depth = get_pr_slice_depth(current_pr)
                        if slice_depth < 2:
                            pr_files_before = set(glob.glob(os.path.join(job_dir, "PR_*.md")))
                            proc = dpopen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), "--slice-failed-pr", current_pr, "--workdir", workdir, "--prd-file", args.prd_file, "--global-dir", global_dir, "--run-dir", run_dir], start_new_session=True, env=get_env_with_gemini_key(f"{base_name}_planner", gemini_api_keys, global_dir))
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
