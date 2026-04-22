import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
import config

def check_vcs(target_dir):
    git_dir = os.path.join(target_dir, ".git")
    if not os.path.exists(git_dir):
        subprocess.run(["git", "init"], cwd=target_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "Baseline commit"], cwd=target_dir, check=True, capture_output=True)

def apply_overlay(target_dir, overlay_path, check_only=False):
    target_dir = Path(target_dir)
    overlay_path = Path(overlay_path)
    
    if not overlay_path.exists():
        return []

    issues = []
    
    for root, dirs, files in os.walk(overlay_path):
        rel_path = Path(root).relative_to(overlay_path)
        dest_dir = target_dir / rel_path
        
        if not check_only:
            dest_dir.mkdir(parents=True, exist_ok=True)
            
        for file in files:
            src_file = Path(root) / file
            
            if file.endswith('.append'):
                base_name = file[:-7]  # remove .append
                dest_file = dest_dir / base_name
                
                with open(src_file, 'r') as f:
                    append_lines = f.read().splitlines()
                    
                existing_lines = []
                if dest_file.exists():
                    with open(dest_file, 'r') as f:
                        existing_lines = f.read().splitlines()
                
                missing_lines = [line for line in append_lines if line and line not in existing_lines]
                
                if missing_lines:
                    if check_only:
                        issues.append(f"Missing lines in {dest_file.relative_to(target_dir)}")
                    else:
                        with open(dest_file, 'a') as f:
                            if existing_lines and existing_lines[-1] != "":
                                f.write('\n')
                            for line in missing_lines:
                                f.write(line + '\n')
            else:
                dest_file = dest_dir / file
                if not dest_file.exists():
                    if check_only:
                        issues.append(f"Missing file {dest_file.relative_to(target_dir)}")
                    else:
                        shutil.copy2(src_file, dest_file)
                        
    return issues

def main():
    parser = argparse.ArgumentParser(description="SDLC Doctor")
    parser.add_argument("target_dir", help="Target project directory")
    parser.add_argument("--fix", action="store_true", help="Apply required infrastructure")
    parser.add_argument("--profile", help="Apply specific profile after base")
    parser.add_argument("--enforce-git-lock", action="store_true", help="Apply optional_hooks/pre-commit")
    
    parser.add_argument("--check", action="store_true", help="Check compliance without making changes")
    
    import json
    
    args = parser.parse_args()
    
    target_dir = os.path.abspath(args.target_dir)
    
    if args.fix:
        check_vcs(target_dir)
        
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    base_overlay = script_dir.parent / "TEMPLATES" / "scaffold" / "base"
    
    config_file = script_dir.parent / "config" / "sdlc_config.json"
    enforce_lock = True
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                cfg = json.load(f)
                enforce_lock = cfg.get("ENFORCE_GIT_LOCK", True)
        except Exception:
            pass
    
    if args.enforce_git_lock:
        enforce_lock = True
    
    issues = apply_overlay(target_dir, base_overlay, check_only=not args.fix)
    
    if args.profile:
        profile_overlay = script_dir.parent / "TEMPLATES" / "scaffold" / "profiles" / args.profile
        profile_issues = apply_overlay(target_dir, profile_overlay, check_only=not args.fix)
        issues.extend(profile_issues)
        
    if enforce_lock:
        pre_commit_src = script_dir.parent / ".sdlc_hooks" / "pre-commit"
        pre_commit_dest = Path(target_dir) / ".git" / "hooks" / "pre-commit"
        
        if pre_commit_src.exists():
            if not args.fix:
                if not pre_commit_dest.exists():
                    issues.append("Missing file .git/hooks/pre-commit")
            else:
                pre_commit_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(pre_commit_src, pre_commit_dest)
                os.chmod(pre_commit_dest, 0o755)
    
    if not args.fix and issues:
        print('[FATAL] Project is not SDLC compliant.')
        # Provide runtime-aware compliance guidance using config.SDLC_RUNTIME_DIR
        print(f'[JIT] To fix: Execute `python3 {config.SDLC_RUNTIME_DIR}/leio-sdlc/scripts/doctor.py --fix {target_dir}`')
        sys.exit(1)
        
if __name__ == "__main__":
    main()