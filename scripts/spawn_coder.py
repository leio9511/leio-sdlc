#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import config
import envelope_assembler
from agent_driver import invoke_agent


def extract_pr_id(pr_file_path):
    basename = os.path.basename(pr_file_path)
    match = re.search(r"^(PR_[\d_]+)", basename, re.IGNORECASE)
    if match:
        return match.group(1).rstrip("_")
    return basename.split(".")[0]


def resolve_coder_artifact_subdir(run_dir, mode):
    if mode == "initial":
        return "initial"

    debug_root = os.path.join(run_dir, "coder_debug")
    prefix = f"{mode}_"
    max_index = 0
    if os.path.isdir(debug_root):
        for entry in os.listdir(debug_root):
            if not entry.startswith(prefix):
                continue
            suffix = entry[len(prefix) :]
            if len(suffix) == 3 and suffix.isdigit():
                max_index = max(max_index, int(suffix))
    return f"{mode}_{max_index + 1:03d}"


def build_coder_startup_packet_and_prompt(workdir, run_dir, pr_file, prd_file, playbook_path, mode, feedback_file=None, system_alert=None):
    references = {
        "pr_contract_file": os.path.abspath(pr_file),
        "prd_file": os.path.abspath(prd_file),
        "playbook_path": os.path.abspath(playbook_path),
    }
    if feedback_file:
        references["feedback_file"] = os.path.abspath(feedback_file)

    contract_params = {}
    if system_alert:
        contract_params["system_alert"] = system_alert

    envelope = envelope_assembler.build_startup_envelope(
        role="coder",
        workdir=os.path.abspath(workdir),
        out_dir=os.path.abspath(run_dir),
        references=references,
        contract_params=contract_params,
        mode=mode,
    )
    rendered_prompt = envelope_assembler.render_envelope_to_prompt(envelope)
    return envelope, rendered_prompt


def save_coder_debug_artifacts(run_dir, mode, envelope, rendered_prompt):
    artifact_subdir = resolve_coder_artifact_subdir(run_dir, mode)
    envelope_assembler.save_envelope_artifacts(
        role="coder",
        out_dir=run_dir,
        envelope=envelope,
        rendered_prompt=rendered_prompt,
        artifact_subdir=artifact_subdir,
    )
    return artifact_subdir


def send_feedback(session_key, message, workdir=".", run_dir="."):
    result = invoke_agent(message, session_key=session_key, role="coder", run_dir=run_dir)
    print(f"Sent feedback to session {result.session_key}")


def handle_feedback_routing(workdir, run_dir, pr_file, prd_file, playbook_path, feedback_file, pr_id, test_mode=False):
    session_file = os.path.join(run_dir, ".coder_session")
    
    if os.path.exists(session_file):
        mode = "revision"
        with open(session_file, "r") as sf:
            session_key = sf.read().strip()
    else:
        mode = "revision_bootstrap"
        session_key = f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"

    envelope, rendered_prompt = build_coder_startup_packet_and_prompt(
        workdir=workdir,
        run_dir=run_dir,
        pr_file=pr_file,
        prd_file=prd_file,
        playbook_path=playbook_path,
        mode=mode,
        feedback_file=feedback_file
    )
    
    save_coder_debug_artifacts(run_dir, mode, envelope, rendered_prompt)

    if test_mode:
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        if mode == "revision_bootstrap":
            with open(session_file, "w") as f:
                f.write("mock-session-key")
        Path("tests").mkdir(exist_ok=True)
        with open("tests/tool_calls.log", "a") as f:
            f.write(rendered_prompt + "\n")
        print('{"status": "mock_success", "role": "coder", "sessionKey": "' + session_key + '"}')
        sys.exit(0)

    if mode == "revision":
        send_feedback(session_key, rendered_prompt, workdir=workdir, run_dir=run_dir)
        return True, session_key
    else:
        result = invoke_agent(rendered_prompt, session_key=session_key, role="coder", run_dir=run_dir)
        with open(session_file, "w") as f:
            f.write(result.session_key)
        print(f"Spawned new session {result.session_key} with feedback")
        return False, result.session_key


def main():
    parser = argparse.ArgumentParser(description="Spawn a coder subagent")
    parser.add_argument("--pr-file", required=True, help="Path to the PR Contract file")
    parser.add_argument("--prd-file", required=True, help="Path to the PRD file")
    parser.add_argument("--feedback-file", required=False, help="Path to the Review Report / Feedback file")
    parser.add_argument("--system-alert", required=False, help="System alert string (e.g. git status)")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument("--global-dir", required=False, help="Global directory for playbooks")
    parser.add_argument("--run-dir", default=".", help="Run directory for artifacts")
    parser.add_argument(
        "--engine",
        choices=["openclaw", "gemini"],
        default=os.environ.get("LLM_DRIVER", config.DEFAULT_LLM_ENGINE),
        help=f"Execution engine to use for the agent driver (default: {config.DEFAULT_LLM_ENGINE})",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SDLC_MODEL", config.DEFAULT_GEMINI_MODEL),
        help=f"Model to use when --engine is gemini (default: {config.DEFAULT_GEMINI_MODEL})",
    )
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("--enable-exec-from-workspace", action="store_true", help="Bypass the workspace path check")
    args = parser.parse_args()

    from handoff_prompter import HandoffPrompter

    if not getattr(args, "enable_exec_from_workspace", False) and not sys.argv[0].startswith(
        getattr(config, "SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))
    ):
        print(HandoffPrompter.get_prompt("startup_validation_failed"))
        sys.exit(1)

    from utils_api_key import setup_spawner_api_key

    setup_spawner_api_key(args, __file__)

    if isinstance(args.engine, str) and args.engine != os.environ.get("LLM_DRIVER"):
        os.environ["LLM_DRIVER"] = args.engine
    if isinstance(args.model, str) and args.model != os.environ.get("SDLC_MODEL"):
        os.environ["SDLC_MODEL"] = args.model

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

    try:
        with open(args.pr_file, "r"):
            pass
        with open(args.prd_file, "r"):
            pass
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    sdlc_root = os.path.dirname(runtime_dir)
    playbook_path = os.path.join(sdlc_root, "playbooks", "coder_playbook.md")
    session_file = os.path.join(args.run_dir, ".coder_session")

    if args.system_alert:
        envelope, rendered_prompt = build_coder_startup_packet_and_prompt(
            workdir=workdir,
            run_dir=args.run_dir,
            pr_file=args.pr_file,
            prd_file=args.prd_file,
            playbook_path=playbook_path,
            mode="system_alert",
            system_alert=args.system_alert
        )
        save_coder_debug_artifacts(args.run_dir, "system_alert", envelope, rendered_prompt)
        
        if test_mode:
            Path(args.run_dir).mkdir(parents=True, exist_ok=True)
            Path("tests").mkdir(exist_ok=True)
            with open("tests/tool_calls.log", "a") as f:
                f.write(rendered_prompt + "\n")
            session_key = "mock-session-key" if os.path.exists(session_file) else f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"
            if not os.path.exists(session_file):
                with open(session_file, "w") as f:
                    f.write(session_key)
            print('{"status": "mock_success", "role": "coder", "sessionKey": "' + session_key + '"}')
            sys.exit(0)

        if os.path.exists(session_file):
            with open(session_file, "r") as sf:
                session_key = sf.read().strip()
            send_feedback(session_key, rendered_prompt, workdir=workdir, run_dir=args.run_dir)
        else:
            session_key = f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"
            result = invoke_agent(rendered_prompt, session_key=session_key, role="coder", run_dir=args.run_dir)
            with open(session_file, "w") as f:
                f.write(result.session_key)
            print(f"Spawned new session {result.session_key} with system alert")
        return

    if args.feedback_file:
        handle_feedback_routing(workdir, args.run_dir, args.pr_file, args.prd_file, playbook_path, args.feedback_file, pr_id, test_mode=test_mode)
        return

    envelope, rendered_prompt = build_coder_startup_packet_and_prompt(
        workdir=workdir,
        run_dir=args.run_dir,
        pr_file=args.pr_file,
        prd_file=args.prd_file,
        playbook_path=playbook_path,
        mode="initial",
    )

    save_coder_debug_artifacts(args.run_dir, "initial", envelope, rendered_prompt)

    if test_mode:
        Path(args.run_dir).mkdir(parents=True, exist_ok=True)
        with open(session_file, "w") as f:
            f.write("mock-session-key")
        Path("tests").mkdir(exist_ok=True)
        with open("tests/tool_calls.log", "a") as f:
            f.write(rendered_prompt + "\n")
        print('{"status": "mock_success", "role": "coder", "sessionKey": "mock-session-key"}')
        sys.exit(0)

    if os.path.exists(session_file):
        with open(session_file, "r") as sf:
            session_key = sf.read().strip()
    else:
        session_key = f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"

    result = invoke_agent(rendered_prompt, session_key=session_key, role="coder", run_dir=args.run_dir)
    if not os.path.exists(session_file):
        with open(session_file, "w") as f:
            f.write(result.session_key)
        print(f"Spawned new session {result.session_key}")


if __name__ == "__main__":
    main()
