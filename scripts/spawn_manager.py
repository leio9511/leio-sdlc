#!/usr/bin/env python3
import argparse
import os
import sys
from agent_driver import invoke_agent, build_prompt
from thinking_resolver import resolve_thinking
import subprocess
import uuid

def main():
    import os, sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", required=False, default=None)
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument(
        "--thinking",
        choices=["low", "medium", "high", "xhigh"],
        default=None,
        help="OpenClaw thinking level (default: high). Only applies when engine is openclaw."
    )
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass the workspace path check")
    args = parser.parse_args()

    # Test mode early exit: must run AFTER argparse so --thinking validation applies.
    # --job-dir is optional here (test-mode regression fix: existing harnesses
    # that set SDLC_TEST_MODE without --job-dir must still exit 0).
    if os.environ.get("SDLC_TEST_MODE") == "true":
        import glob
        job_dir = args.job_dir
        # Sys.argv fallback for backward compatibility with callers that
        # pass --job-dir but the parser didn't populate it (shouldn't happen
        # post-restructure, but preserved for safety).
        if not job_dir and "--job-dir" in sys.argv:
            try:
                idx = sys.argv.index("--job-dir")
                job_dir = sys.argv[idx + 1]
            except (ValueError, IndexError):
                pass
        if job_dir:
            for pr in glob.glob(os.path.join(job_dir, "*.md")):
                with open(pr, "w") as f: f.write("status: closed\n")
        print("[DONE]")
        sys.exit(0)

    import config
    from handoff_prompter import HandoffPrompter
    from runtime_launch_guard import is_authorized_runtime_launch
    if not getattr(args, "enable_exec_from_workspace", False) and not is_authorized_runtime_launch(sys.argv[0]):
        print(HandoffPrompter.get_prompt("startup_validation_failed"))
        sys.exit(1)
    # API Key Assignment
    from utils_api_key import setup_spawner_api_key
    setup_spawner_api_key(args, __file__)

    # Resolve job_dir with sys.argv fallback for backward compatibility
    job_dir = args.job_dir
    if not job_dir and "--job-dir" in sys.argv:
        try:
            idx = sys.argv.index("--job-dir")
            job_dir = sys.argv[idx + 1]
        except (ValueError, IndexError):
            pass
    if not job_dir:
        print("Error: --job-dir is required", file=sys.stderr)
        sys.exit(1)

    resolved_thinking = resolve_thinking(args.thinking)

    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    skill_md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md")
    with open(skill_md_path, "r") as f:
        skill_text = f.read()

    task_string = build_prompt("manager",
        workdir=workdir,
        job_dir=job_dir,
        skill_text=skill_text
    )
    
    session_id = f"mgr-{uuid.uuid4().hex[:8]}"
    result = invoke_agent(task_string, session_key=session_id, role="manager", thinking=resolved_thinking)

if __name__ == "__main__":
    main()
