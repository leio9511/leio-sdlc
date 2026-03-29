import re

with open("scripts/orchestrator.py", "r") as f:
    content = f.read()

# Make workdir and prd-file not required, then check them later if not cleanup
content = content.replace('parser.add_argument("--workdir", required=True)', 'parser.add_argument("--workdir", required=False)')
content = content.replace('parser.add_argument("--prd-file", required=True)', 'parser.add_argument("--prd-file", required=False)')

check_logic = """    if not args.cleanup and (not args.workdir or not args.prd_file):
        parser.error("the following arguments are required: --workdir, --prd-file")

"""
content = content.replace('args = parser.parse_args()', f'args = parser.parse_args()\n{check_logic}')

# Replace cleanup logic
old_cleanup = """    if args.cleanup:
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
        branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch_output = branch_res.stdout.strip()
        if branch_output in ["master", "main"]:
            print("Cannot quarantine master/main branch.")
            sys.exit(1)
            
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
        timestamp = int(time.time())
        subprocess.run(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
        subprocess.run(["git", "checkout", "master"], check=False)
        
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

        sys.exit(0)"""

new_cleanup = """    if args.cleanup:
        lock_dir = os.path.expanduser("~/.openclaw/workspace/locks")
        if not os.path.exists(lock_dir):
            sys.exit(0)
            
        for lock_file in glob.glob(os.path.join(lock_dir, "*.lock")):
            try:
                with open(lock_file, "r") as f:
                    content = f.read()
                if not content.strip():
                    continue
                import json
                data = json.loads(content)
                pid = data.get("pid")
                active_workdir = data.get("active_workdir")
                if not pid or not active_workdir:
                    continue
                
                # Liveness Check
                is_alive = True
                try:
                    os.kill(pid, 0)
                except OSError:
                    is_alive = False
                    
                if is_alive:
                    continue # Skip alive pipelines
                    
                # Pipeline is dead, execute forensic quarantine protocol in active_workdir
                if os.path.exists(active_workdir):
                    os.chdir(active_workdir)
                    branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
                    branch_output = branch_res.stdout.strip()
                    if branch_output not in ["master", "main"]:
                        subprocess.run(["git", "add", "-A"], check=False)
                        subprocess.run(["git", "commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"], check=False)
                        import time
                        timestamp = int(time.time())
                        subprocess.run(["git", "branch", "-m", f"{branch_output}_crashed_{timestamp}"], check=False)
                        subprocess.run(["git", "checkout", "master"], check=False)
                        
                    for lockfile_name in [".coder_session", ".sdlc_repo.lock"]:
                        try:
                            os.remove(os.path.join(active_workdir, lockfile_name))
                        except OSError:
                            pass
                            
                    manifest_path = os.path.join(active_workdir, ".sdlc_lock_manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, "r") as f:
                                manifest_data = json.load(f)
                            for m_lock_path in manifest_data.get("locks", []):
                                try:
                                    if os.path.exists(m_lock_path):
                                        os.remove(m_lock_path)
                                except OSError:
                                    pass
                            os.remove(manifest_path)
                        except Exception as e:
                            pass
                            
                # Safely delete the stale lock file
                try:
                    os.remove(lock_file)
                except OSError:
                    pass
            except Exception as e:
                # Malformed or inaccessible lock
                continue
                
        sys.exit(0)"""

content = content.replace(old_cleanup, new_cleanup)

with open("scripts/orchestrator.py", "w") as f:
    f.write(content)

print("Patch applied")
