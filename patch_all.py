import re
import os
import signal
import time
import fcntl

# 1. Update scripts/handoff_prompter.py
with open("scripts/handoff_prompter.py", "r") as f:
    text = f.read()

text = text.replace(
    '"git_checkout_error": "[FATAL_GIT]\\n[ACTION REQUIRED FOR MANAGER]\\nGit checkout failed. You must run `git branch -D` and `git clean -fd` to resolve the state.",',
    '"git_checkout_error": "[FATAL_GIT] Git checkout failed. Workspace preserved. Invoke --cleanup to quarantine.",\n        "fatal_crash": "[FATAL_CRASH] Orchestrator crashed. Process groups reaped. Workspace preserved. Read traceback. Invoke --cleanup to quarantine the branch.",\n        "fatal_interrupt": "[FATAL_INTERRUPT] Aborted via SIGINT/SIGTERM. Process groups reaped. Workspace preserved.",'
)

with open("scripts/handoff_prompter.py", "w") as f:
    f.write(text)

# 2. Update docs/TEMPLATES/organization_governance.md (using absolute path)
gov_path = "/root/.openclaw/workspace/projects/docs/TEMPLATES/organization_governance.md"
if os.path.exists(gov_path):
    with open(gov_path, "r") as f:
        gov = f.read()

    old_42 = '''4.2 Toxic Branch Anti-Manual Merge
The Planner and Coder must never manually merge a branch that has failed a review or been flagged as "Toxic". All branch cleanup must be handled via the Orchestrator's standard reset mechanisms.'''

    new_42 = '''4.2 Toxic Branch Anti-Manual Merge & Forensic Quarantine
In the event of an aborted or crashed pipeline (indicated by [FATAL_CRASH] or [FATAL_INTERRUPT]), the current branch must NOT be manually merged or force-pushed. The Orchestrator's `--cleanup` protocol MUST be invoked to:
1. Acquire an exclusive fcntl lock on the repository.
2. Create a WIP 'Forensic' commit of the current state.
3. Rename the toxic branch with a `{branch}_crashed_{timestamp}` suffix.
4. Return the workspace to a clean 'master' state.
Manual deletion of the repository lock or bypassing the quarantine is a direct violation of the SDLC safety protocol.'''

    gov = gov.replace(old_42, new_42)
    with open(gov_path, "w") as f:
        f.write(gov)
else:
    print(f"Warning: {gov_path} not found. Skipping.")

# 3. Create tests/test_reaper_logic.py
test_content = '''import os
import subprocess
import signal
import time
import sys

def test_reaper():
    test_script = os.path.join(os.getcwd(), 'tests', 'reaper_dummy.py')
    with open(test_script, 'w') as f:
        f.write(\"\"\"
import os
import subprocess
import signal
import time
import sys

def run_isolated_child():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"], start_new_session=True)

proc = None
try:
    proc = run_isolated_child()
    print(f"CHILD_PID:{proc.pid}")
    sys.stdout.flush()
    raise KeyboardInterrupt
finally:
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            pass
\"\"\")

    proc = subprocess.Popen([sys.executable, test_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate()
    
    child_pid = None
    for line in out.splitlines():
        if "CHILD_PID:" in line:
            child_pid = int(line.split(":")[1])
    
    if child_pid:
        time.sleep(0.5)
        try:
            os.kill(child_pid, 0)
            print(f"FAILURE: Child process {child_pid} still alive.")
            sys.exit(1)
        except OSError:
            print(f"SUCCESS: Child process {child_pid} reaped.")
    else:
        print("FAILURE: Could not determine child PID.")
        sys.exit(1)

if __name__ == '__main__':
    test_reaper()
'''
os.makedirs("tests", exist_ok=True)
with open("tests/test_reaper_logic.py", "w") as f:
    f.write(test_content)

# 4. Patch orchestrator.py
with open("scripts/orchestrator.py", "r") as f:
    orch = f.read()

# Add imports
orch = orch.replace("import fcntl\n", "import fcntl\nimport signal\nimport traceback\n")

# Cleanup flag
cleanup_code = """
    parser.add_argument("--cleanup", action="store_true", help="Quarantine crashed orchestrator state")
    args = parser.parse_args()

    if args.cleanup:
        lock_path = os.path.join(args.workdir, ".sdlc_repo.lock")
        try:
            f_lock = open(lock_path, "w")
            fcntl.flock(f_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError):
            print("[FATAL_LOCK] Cannot clean up while another SDLC pipeline is active.")
            sys.exit(1)
        
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
        
        for lockfile in [".coder_session", ".sdlc_repo.lock"]:
            try:
                os.remove(os.path.join(args.workdir, lockfile))
            except OSError:
                pass
        sys.exit(0)
"""
orch = orch.replace('    args = parser.parse_args()\n', cleanup_code)

# Try/finally wrap
parts = orch.split('    loops = 0\n    while True:')
if len(parts) >= 2:
    before = parts[0]
    after = parts[1]
    
    after_parts = after.split('if __name__ == "__main__":')
    body = after_parts[0]
    
    indented_body = ""
    for line in body.splitlines(True):
        if line.strip() == "":
            indented_body += line
        else:
            indented_body += "    " + line
            
    finally_block = """
    except SystemExit as e:
        if str(e) == "1":
            print(HandoffPrompter.get_prompt("fatal_interrupt"))
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
                pass

if __name__ == "__main__":"""
    
    wrap_start = """
    proc = None

    def sig_handler(signum, frame):
        raise SystemExit(1)
    
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    try:
        loops = 0
        while True:"""
    
    orch = before + wrap_start + indented_body + finally_block + after_parts[1]

# Popen replacements
def replace_with_indent(pattern, replacement_template, text):
    def repl(m):
        indent = m.group(1)
        args = m.group(2)
        rep = replacement_template.format(args=args).replace('\n', '\n' + indent)
        return indent + rep
    return re.sub(pattern, repl, text)

# Popen 1
p1 = r'^([ \t]*)subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_planner\.py"\), (.*?)\], check=True\)'
r1 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), {args}], start_new_session=True)
proc.wait()
if proc.returncode != 0: raise subprocess.CalledProcessError(proc.returncode, "spawn_planner.py")'''
orch = replace_with_indent(p1, r1, orch)

# Popen 2
p2 = r'^([ \t]*)subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_planner\.py"\), (.*?)\]\)'
r2 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_planner.py"), {args}], start_new_session=True)
proc.wait()'''
orch = replace_with_indent(p2, r2, orch)

# Popen 3
p3 = r'^([ \t]*)coder_result = subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_coder\.py"\), (.*?)\], timeout=MAX_RUNTIME\)'
r3 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), {args}], start_new_session=True)
try:
    proc.wait(timeout=MAX_RUNTIME)
except subprocess.TimeoutExpired:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    raise
class _CoderRes: pass
coder_result = _CoderRes()
coder_result.returncode = proc.returncode'''
orch = replace_with_indent(p3, r3, orch)

# Popen 4
p4 = r'^([ \t]*)subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_coder\.py"\), (.*?)\]\)'
r4 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_coder.py"), {args}], start_new_session=True)
proc.wait()'''
orch = replace_with_indent(p4, r4, orch)

# Popen 5
p5 = r'^([ \t]*)subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_reviewer\.py"\), (.*?)\]\)'
r5 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_reviewer.py"), {args}], start_new_session=True)
proc.wait()'''
orch = replace_with_indent(p5, r5, orch)

# Popen 6
p6 = r'^([ \t]*)arbitrator_result = subprocess\.run\(\[sys\.executable, os\.path\.join\(RUNTIME_DIR, "spawn_arbitrator\.py"\), (.*?)\], capture_output=True, text=True\)'
r6 = '''proc = subprocess.Popen([sys.executable, os.path.join(RUNTIME_DIR, "spawn_arbitrator.py"), {args}], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out, err = proc.communicate()
class _ArbRes: pass
arbitrator_result = _ArbRes()
arbitrator_result.stdout = out'''
orch = replace_with_indent(p6, r6, orch)

with open("scripts/orchestrator.py", "w") as f:
    f.write(orch)

