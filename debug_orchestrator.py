PROJECT_ROOT = "/root/.openclaw/workspace/projects/leio-sdlc"
SANDBOX = "/tmp/debug_sandbox"
import os, subprocess, shutil, sys

if os.path.exists(SANDBOX): shutil.rmtree(SANDBOX)
os.makedirs(SANDBOX)
os.chdir(SANDBOX)
subprocess.run(["git", "init"])
subprocess.run(["git", "config", "user.name", "Test"])
subprocess.run(["git", "config", "user.email", "test@example.com"])
subprocess.run(["git", "commit", "--allow-empty", "-m", "init"])
with open("prd.md", "w") as f: f.write("test prd")

# Let's run it with a simple print inside the script to see where it stops
print("Running orchestrator...")
proc = subprocess.run([
    "python3", "-c", "import sys; sys.path.insert(0, '/root/.openclaw/workspace/projects/leio-sdlc/scripts'); import orchestrator; print('Orchestrator imported successfully')"
], capture_output=True, text=True)

print("STDOUT:", proc.stdout)
print("STDERR:", proc.stderr)
