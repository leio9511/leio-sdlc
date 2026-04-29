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

    # Use the same prefix for both system_alert and system_alert_bootstrap
    # to maintain continuity of the alert cycle numbering as requested.
    prefix = f"{mode}_"
    if mode == "system_alert_bootstrap":
        prefix = "system_alert_"

    debug_root = os.path.join(run_dir, "coder_debug")
    max_index = 0
    if os.path.isdir(debug_root):
        for entry in os.listdir(debug_root):
            if not entry.startswith(prefix):
                continue
            suffix = entry[len(prefix) :]
            if len(suffix) == 3 and suffix.isdigit():
                max_index = max(max_index, int(suffix))
    return f"{prefix}{max_index + 1:03d}"


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


REVISION_CONTINUATION_RULE = "Do not restart problem-solving from scratch. Modify the existing implementation to satisfy the reviewer findings."
SYSTEM_ALERT_CONTINUATION_RULE = "Do not re-plan the whole PR. Fix the exact operational failure shown below, rerun validation, and continue from the current branch state."
RECOVERY_CONTINUATION_WARNING = "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts."


def get_current_branch(workdir):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workdir,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_latest_commit_hash(workdir):
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=workdir,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def read_text_file(path):
    with open(path, "r") as f:
        return f.read()


def build_coder_continuation_packet(
    mode,
    workdir,
    pr_file,
    prd_file,
    playbook_path,
    feedback_file=None,
    current_branch=None,
    latest_commit_hash=None,
):
    references = {
        "pr_contract_file": os.path.abspath(pr_file),
        "prd_file": os.path.abspath(prd_file),
        "playbook_path": os.path.abspath(playbook_path),
    }
    reference_index = [
        {
            "id": "pr_contract",
            "kind": "pr_contract",
            "path": references["pr_contract_file"],
            "required": True,
            "priority": 1,
            "purpose": "execution_contract_source",
        },
        {
            "id": "prd",
            "kind": "prd",
            "path": references["prd_file"],
            "required": True,
            "priority": 1,
            "purpose": "authoritative_requirements",
        },
        {
            "id": "coder_playbook",
            "kind": "playbook",
            "path": references["playbook_path"],
            "required": True,
            "priority": 1,
            "purpose": "coder_operating_rules",
        },
    ]
    if feedback_file:
        references["feedback_file"] = os.path.abspath(feedback_file)
        reference_index.append(
            {
                "id": "reviewer_feedback",
                "kind": "feedback",
                "path": references["feedback_file"],
                "required": True,
                "priority": 1,
                "purpose": "inline_actionable_revision_findings",
            }
        )

    if mode == "revision":
        lifecycle = "same_session_delta_continuation"
        prompt_kind = "coder_revision_continuation"
        behavioral_rules = [REVISION_CONTINUATION_RULE]
        continuation_semantics = {
            "fresh_task": False,
            "existing_branch_state_authoritative": True,
            "same_session_required": True,
            "inline_review_section": "# REVIEW REPORT JSON",
        }
    elif mode == "revision_bootstrap":
        lifecycle = "recovery_bootstrap_continuation"
        prompt_kind = "coder_revision_recovery_bootstrap"
        behavioral_rules = [RECOVERY_CONTINUATION_WARNING]
        continuation_semantics = {
            "fresh_task": False,
            "existing_branch_state_authoritative": True,
            "same_session_required": False,
            "inline_review_section": "# REVIEW REPORT JSON",
        }
    elif mode == "system_alert":
        lifecycle = "same_session_operational_delta_continuation"
        prompt_kind = "coder_system_alert_continuation"
        behavioral_rules = [SYSTEM_ALERT_CONTINUATION_RULE]
        continuation_semantics = {
            "fresh_task": False,
            "existing_branch_state_authoritative": True,
            "same_session_required": True,
            "inline_alert_section": "# SYSTEM ALERT YOU MUST FIX",
        }
    elif mode == "system_alert_bootstrap":
        lifecycle = "recovery_bootstrap_continuation"
        prompt_kind = "coder_system_alert_recovery_bootstrap"
        behavioral_rules = [RECOVERY_CONTINUATION_WARNING]
        continuation_semantics = {
            "fresh_task": False,
            "existing_branch_state_authoritative": True,
            "same_session_required": False,
            "inline_alert_section": "# SYSTEM ALERT YOU MUST FIX",
        }
    else:
        lifecycle = "coder_continuation"
        prompt_kind = f"coder_{mode}_continuation"
        behavioral_rules = []
        continuation_semantics = {}

    if mode in ["revision", "revision_bootstrap"]:
        final_checklist = [
            "Address the reviewer findings with code changes, not acknowledgment-only output.",
            "Keep all work inside the locked working directory and preserve branch guardrails.",
            "Run the relevant tests and `./preflight.sh` if it exists until green.",
            "Commit the exact files you changed and leave `git status` clean.",
            "Report the latest commit hash when handing work back.",
        ]
    elif mode in ["system_alert", "system_alert_bootstrap"]:
        final_checklist = [
            "Fix the exact operational failure shown in the alert.",
            "Keep all work inside the locked working directory and preserve branch guardrails.",
            "Run the relevant tests and `./preflight.sh` if it exists until green.",
            "Commit the exact files you changed and leave `git status` clean.",
            "Report the latest commit hash when handing work back.",
        ]
    else:
        final_checklist = [
            "Address the findings with code changes.",
            "Keep all work inside the locked working directory and preserve branch guardrails.",
            "Run the relevant tests and `./preflight.sh` if it exists until green.",
            "Commit the exact files you changed and leave `git status` clean.",
            "Report the latest commit hash when handing work back.",
        ]

    return {
        "role": "coder",
        "mode": mode,
        "lifecycle": lifecycle,
        "prompt_kind": prompt_kind,
        "references": references,
        "reference_index": reference_index,
        "current_branch": current_branch,
        "latest_commit_hash": latest_commit_hash,
        "behavioral_rules": behavioral_rules,
        "continuation_semantics": continuation_semantics,
        "final_checklist": final_checklist,
    }


def _append_coder_context(lines, workdir, pr_file, prd_file, playbook_path, feedback_file=None, current_branch=None, latest_commit_hash=None):
    lines.extend(
        [
            "# SUPPORTING CONTEXT",
            f"- Locked workdir: `{os.path.abspath(workdir)}`",
            f"- PR contract path: `{os.path.abspath(pr_file)}`",
            f"- PRD path: `{os.path.abspath(prd_file)}`",
            f"- Coder playbook path: `{os.path.abspath(playbook_path)}`",
        ]
    )
    if feedback_file:
        lines.append(f"- Feedback file path: `{os.path.abspath(feedback_file)}`")
    if current_branch:
        lines.append(f"- Current branch: `{current_branch}`")
    if latest_commit_hash:
        lines.append(f"- Latest commit hash: `{latest_commit_hash}`")

    lines.extend(
        [
            "",
            "# VALIDATION AND GIT HYGIENE REMINDERS",
            "- Stay on the current feature branch; never switch branches and never work on `master` or `main`.",
            "- Do not `git push`.",
            "- Use explicit `git add <file>` only for files you changed; never use `git add .`.",
            "- Run the relevant tests and `./preflight.sh` if it exists until green.",
            "- Commit the exact files you changed, leave `git status` clean, then report `LATEST_HASH=$(git rev-parse HEAD)`.",
        ]
    )


def build_coder_revision_continuation_prompt(
    workdir,
    pr_file,
    prd_file,
    playbook_path,
    review_report_json,
    feedback_file=None,
    current_branch=None,
    latest_commit_hash=None,
):
    lines = [
        "# CODER REVISION CONTINUATION",
        "This is a same-session revision continuation, not a fresh task. Existing branch state and code are the starting point.",
        REVISION_CONTINUATION_RULE,
        "The current implementation is authoritative; inspect it, patch it, and validate the specific reviewer findings below.",
        "",
        "# REVIEW REPORT JSON",
        review_report_json,
        "",
    ]
    _append_coder_context(lines, workdir, pr_file, prd_file, playbook_path, feedback_file, current_branch, latest_commit_hash)
    return "\n".join(lines)


def build_coder_revision_recovery_prompt(
    workdir,
    pr_file,
    prd_file,
    playbook_path,
    review_report_json,
    feedback_file=None,
    current_branch=None,
    latest_commit_hash=None,
):
    lines = [
        "# CODER REVISION RECOVERY CONTINUATION",
        RECOVERY_CONTINUATION_WARNING,
        "Prioritize restoring task context from the existing branch and fixing the reviewer findings before rereading supporting references.",
        "The current implementation is authoritative; do not discard or restart the work already present on disk.",
        "",
        "# REVIEW REPORT JSON",
        review_report_json,
        "",
    ]
    _append_coder_context(lines, workdir, pr_file, prd_file, playbook_path, feedback_file, current_branch, latest_commit_hash)
    return "\n".join(lines)


def build_coder_system_alert_continuation_prompt(
    workdir,
    pr_file,
    prd_file,
    playbook_path,
    system_alert,
    current_branch=None,
    latest_commit_hash=None,
):
    lines = [
        "# CODER SYSTEM ALERT CONTINUATION",
        "This is a same-session operational correction. Focus only on the failure below and preserve the current branch state.",
        SYSTEM_ALERT_CONTINUATION_RULE,
        "",
        "# SYSTEM ALERT YOU MUST FIX",
        system_alert,
        "",
    ]
    _append_coder_context(lines, workdir, pr_file, prd_file, playbook_path, None, current_branch, latest_commit_hash)
    return "\n".join(lines)


def build_coder_system_alert_recovery_prompt(
    workdir,
    pr_file,
    prd_file,
    playbook_path,
    system_alert,
    current_branch=None,
    latest_commit_hash=None,
):
    lines = [
        "# CODER SYSTEM ALERT RECOVERY CONTINUATION",
        RECOVERY_CONTINUATION_WARNING,
        "The immediate objective is corrective action for the operational failure below, not replanning the PR.",
        "Recover context from the current branch, fix the exact failure, rerun validation, commit if needed, and leave the workspace clean.",
        "",
        "# SYSTEM ALERT YOU MUST FIX",
        system_alert,
        "",
    ]
    _append_coder_context(lines, workdir, pr_file, prd_file, playbook_path, None, current_branch, latest_commit_hash)
    return "\n".join(lines)


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
    current_branch = get_current_branch(workdir)
    latest_commit_hash = get_latest_commit_hash(workdir)
    review_report_json = read_text_file(feedback_file)
    
    if os.path.exists(session_file):
        mode = "revision"
        session_key = read_text_file(session_file).strip()
        rendered_prompt = build_coder_revision_continuation_prompt(
            workdir=workdir,
            pr_file=pr_file,
            prd_file=prd_file,
            playbook_path=playbook_path,
            review_report_json=review_report_json,
            feedback_file=feedback_file,
            current_branch=current_branch,
            latest_commit_hash=latest_commit_hash,
        )
    else:
        mode = "revision_bootstrap"
        session_key = f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"
        rendered_prompt = build_coder_revision_recovery_prompt(
            workdir=workdir,
            pr_file=pr_file,
            prd_file=prd_file,
            playbook_path=playbook_path,
            review_report_json=review_report_json,
            feedback_file=feedback_file,
            current_branch=current_branch,
            latest_commit_hash=latest_commit_hash,
        )

    packet = build_coder_continuation_packet(
        mode=mode,
        workdir=workdir,
        pr_file=pr_file,
        prd_file=prd_file,
        playbook_path=playbook_path,
        feedback_file=feedback_file,
        current_branch=current_branch,
        latest_commit_hash=latest_commit_hash,
    )
    
    save_coder_debug_artifacts(run_dir, mode, packet, rendered_prompt)

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


def handle_system_alert_routing(workdir, run_dir, pr_file, prd_file, playbook_path, system_alert, pr_id, test_mode=False):
    session_file = os.path.join(run_dir, ".coder_session")
    current_branch = get_current_branch(workdir)
    latest_commit_hash = get_latest_commit_hash(workdir)
    
    if os.path.exists(session_file):
        mode = "system_alert"
        session_key = read_text_file(session_file).strip()
        rendered_prompt = build_coder_system_alert_continuation_prompt(
            workdir=workdir,
            pr_file=pr_file,
            prd_file=prd_file,
            playbook_path=playbook_path,
            system_alert=system_alert,
            current_branch=current_branch,
            latest_commit_hash=latest_commit_hash,
        )
    else:
        mode = "system_alert_bootstrap"
        session_key = f"sdlc_coder_{pr_id}_{uuid.uuid4().hex[:8]}"
        rendered_prompt = build_coder_system_alert_recovery_prompt(
            workdir=workdir,
            pr_file=pr_file,
            prd_file=prd_file,
            playbook_path=playbook_path,
            system_alert=system_alert,
            current_branch=current_branch,
            latest_commit_hash=latest_commit_hash,
        )

    packet = build_coder_continuation_packet(
        mode=mode,
        workdir=workdir,
        pr_file=pr_file,
        prd_file=prd_file,
        playbook_path=playbook_path,
        current_branch=current_branch,
        latest_commit_hash=latest_commit_hash,
    )
    
    save_coder_debug_artifacts(run_dir, mode, packet, rendered_prompt)

    if test_mode:
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        if mode == "system_alert_bootstrap":
            with open(session_file, "w") as f:
                f.write("mock-session-key")
        Path("tests").mkdir(exist_ok=True)
        with open("tests/tool_calls.log", "a") as f:
            f.write(rendered_prompt + "\n")
        print('{"status": "mock_success", "role": "coder", "sessionKey": "' + session_key + '"}')
        sys.exit(0)

    if mode == "system_alert":
        send_feedback(session_key, rendered_prompt, workdir=workdir, run_dir=run_dir)
        return True, session_key
    else:
        result = invoke_agent(rendered_prompt, session_key=session_key, role="coder", run_dir=run_dir)
        with open(session_file, "w") as f:
            f.write(result.session_key)
        print(f"Spawned new session {result.session_key} with system alert")
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
        handle_system_alert_routing(workdir, args.run_dir, args.pr_file, args.prd_file, playbook_path, args.system_alert, pr_id, test_mode=test_mode)
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
