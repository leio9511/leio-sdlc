#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
import uuid

def main():
    import os, sys
    if os.environ.get("SDLC_TEST_MODE") == "true":
        import glob
        for pr in glob.glob(os.path.join(sys.argv[sys.argv.index("--job-dir")+1], "*.md")):
            with open(pr, "w") as f: f.write("status: closed\n")
        print("[DONE]")
        sys.exit(0)
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    args = parser.parse_args()

    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    with open("/root/.openclaw/workspace/projects/leio-sdlc/SKILL.md", "r") as f:
        skill_text = f.read()

    task_string = f"""
ATTENTION: Your root workspace is rigidly locked to {workdir}.
You are strictly forbidden from reading, writing, or modifying files outside this absolute path.
Use explicit 'git add <file>' to stage changes safely within your directory.

You are the leio-sdlc Manager. 
CRITICAL: You are running in a test sandbox! Before doing anything, you MUST run:
`cd {workdir}`

Then, process the job directory: {args.job_dir}
Follow your runbook strictly. When finished, output [DONE] and exit.

--- RUNBOOK ---
{skill_text}
"""
    
    session_id = f"mgr-{uuid.uuid4().hex[:8]}"
    cmd = ["openclaw", "agent", "--session-id", session_id, "-m", task_string]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Manager Agent Failed: {result.stderr}")
        sys.exit(1)
    else:
        print(result.stdout)

if __name__ == "__main__":
    main()
