import argparse
import tempfile
import os
import json
import sys
import subprocess
import uuid
import re

def main():
    parser = argparse.ArgumentParser(description="Spawn Planner Agent")
    parser.add_argument("--prd-file", required=True, help="Path to the PRD file")
    parser.add_argument("--out-dir", required=False, default=None, help="Output directory for PRs")
    parser.add_argument("--workdir", required=True, help="Working directory lock")
    parser.add_argument("--slice-failed-pr", required=False, default=None, help="Path to a failed PR file to slice")
    parser.add_argument("--global-dir", required=False, help="Global directory for templates")
    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
    args = parser.parse_args()

    workdir = os.path.abspath(args.workdir)
    os.chdir(workdir)

    if args.out_dir is None:
        # Dynamically compute job directory from PRD filename
        prd_filename = os.path.basename(args.prd_file)
        base_name, _ = os.path.splitext(prd_filename)
        args.out_dir = os.path.join(".sdlc_runs", base_name)

    os.makedirs(args.out_dir, exist_ok=True)

    if not (os.path.isfile(args.prd_file) and os.path.getsize(args.prd_file) > 0):
        print(f"[Pre-flight Failed] Planner cannot start. PRD file not found at '{args.prd_file}'. You must read or create the PRD first.")
        sys.exit(1)

    failed_pr_content = None
    failed_pr_id = None
    if args.slice_failed_pr is not None:
        if not (os.path.isfile(args.slice_failed_pr) and os.path.getsize(args.slice_failed_pr) > 0):
            print(f"[Pre-flight Failed] Planner cannot start. Failed PR file not found or empty at '{args.slice_failed_pr}'.")
            sys.exit(1)
        with open(args.slice_failed_pr, "r") as f:
            failed_pr_content = f.read()
            
        failed_pr_filename = os.path.basename(args.slice_failed_pr)
        match = re.match(r"^PR_(\d+(?:_\d+)*)_", failed_pr_filename)
        if match:
            failed_pr_id = match.group(1)
        else:
            print(f"[Warning] Could not extract failed PR ID from filename '{failed_pr_filename}'. Falling back to default append mode.")

    # Dynamic Toolchain Addressing
    SDLC_DIR = os.path.dirname(os.path.abspath(__file__))
    global_dir = os.path.abspath(args.global_dir) if args.global_dir else os.path.dirname(RUNTIME_DIR)

    # Scaffolding: Ensure new project has standard guardrail and ignore files
    scaffold_files = {
        ".gitignore": ".gitignore",
        ".sdlc_guardrail": ".sdlc_guardrail",
        ".release_ignore": ".release_ignore"
    }
    for filename, source in scaffold_files.items():
        target_path = os.path.join(workdir, filename)
        if not os.path.exists(target_path):
            source_path = os.path.join(SDLC_DIR, "..", source)
            if os.path.exists(source_path):
                import shutil
                shutil.copy(source_path, target_path)
                print(f"[Scaffold] Inherited {filename} from framework.")
            else:
                # Fallback if source is missing in framework root
                pass
    
    contract_script = os.path.join(SDLC_DIR, "create_pr_contract.py")

    try:
        with open(args.prd_file, "r") as f:
            prd_content = f.read()
    except FileNotFoundError:
        print(f"Error: PRD file not found: {args.prd_file}")
        sys.exit(1)
        
    try:
        with open(os.path.join(global_dir, "TEMPLATES", "PR_Contract.md.template"), "r") as tf:
            template_content = tf.read()
    except FileNotFoundError:
        template_content = "status: open\n\n# PR-[ID]: [Title]\n\n## 1. Objective\n\n## 2. Scope & Implementation Details\n\n## 3. TDD & Acceptance Criteria\n"

    playbook_path = os.path.join(global_dir, "playbooks", "planner_playbook.md")
    playbook_content = ""
    if os.path.exists(playbook_path):
        with open(playbook_path, "r") as f:
            playbook_content = f.read()

    if args.slice_failed_pr is not None:
        insert_after_flag = f" --insert-after {failed_pr_id}" if failed_pr_id else ""
        task_string = (
            f"The following PR has failed multiple times because it is too complex for the Coder. "
            f"Your task is to break THIS SPECIFIC PR down into at least 2 smaller, sequential Micro-PRs. "
            f"Do not change the overall goal of the project, just reduce the scope per PR. "
            f"Use the original PRD for context.\\n\\n"
            f"You are explicitly forbidden from manually editing the markdown file's status field.\\n\\n"
            f"--- PLANNER PLAYBOOK ---\\n{playbook_content}\\n------------------------\\n\\n"
            f"FAILED PR:\\n{failed_pr_content}\\n\\n"
            f"ORIGINAL PRD:\\n{prd_content}\\n\\n"
            f"ATTENTION: Your root workspace is rigidly locked to {workdir}. "
            f"You MUST use `python3 {contract_script} --workdir {workdir} --job-dir {args.out_dir}{insert_after_flag} --title <title> --content-file <file>` "
            f"to generate the PR contracts instead of raw file writing. "
            f"The `--insert-after` parameter is MANDATORY for sequential ordering of the new sliced PRs.\\n"
            f"For EVERY Micro-PR you generate, you MUST strictly use the format defined in the template below. "
            f"Do NOT alter the `status: open` YAML frontmatter.\\n"
            f"TEMPLATE:\\n{template_content}\\n"
            f"TDD GUARDRAIL: Every PR must be a self-contained, mergeable unit. You CANNOT write a failing test in PR_1 and fix it in PR_2. A single PR must include BOTH the test and the implementation so it passes the pipeline cleanly. "
            f"You MUST generate at least 2 Micro-PRs for this feature. Start now."
        )
    else:
        task_string = (
            f"ATTENTION: Your root workspace is rigidly locked to {workdir}. "
            f"You are strictly forbidden from reading, writing, or modifying files outside this absolute path. "
            f"Use explicit 'git add <file>' to stage changes safely within your directory.\\n\\n"
            f"You are explicitly forbidden from manually editing the markdown file's status field.\\n\\n"
            f"--- PLANNER PLAYBOOK ---\\n{playbook_content}\\n------------------------\\n\\n"
            f"You are the leio-sdlc Planner. Please analyze the following PRD:\\n{prd_content}\\n\\n"
            f"CORE INSTRUCTION: You are forbidden from generating a single monolithic PR contract. "
            f"You must break the PRD down into a functional, dependency-ordered chain of Micro-PRs without hardcoding specific file paths. Give implementation freedom to the Coder. "
            f"TDD GUARDRAIL: Every PR must be a fully working, self-contained increment. The CI pipeline runs at the end of EVERY PR and requires 100% green tests to merge. You CANNOT split writing a failing test into PR_1 and fixing it in PR_2. A single PR must include BOTH the test and the implementation. "
            f"You MUST use `python3 {contract_script} --workdir {workdir} --job-dir {args.out_dir} --title <title> --content-file <file>` "
            f"to generate the PR contracts instead of raw file writing. "
            f"For EVERY Micro-PR you generate, you MUST strictly use the format defined in the template below. "
            f"Do NOT alter the `status: open` YAML frontmatter.\\n"
            f"TEMPLATE:\\n{template_content}\\n"
            f"Start now."
        )

    test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"

    if test_mode:
        os.makedirs("tests", exist_ok=True)
        log_entry = str({'tool': 'spawn_planner', 'args': {'prd_file': args.prd_file, 'workdir': workdir, 'contract_script': contract_script, 'slice_failed_pr': args.slice_failed_pr}})
        with open("tests/tool_calls.log", "a") as f:
            f.write(log_entry + "\\n")
        
        with open("tests/task_string.log", "a") as f:
            f.write(task_string + "\\n")

        if args.slice_failed_pr is not None:
            with open(os.path.join(args.out_dir, "PR_Slice_1.md"), "w") as f:
                f.write("status: open\\n\\n# PR-001: Slice 1\\n\\n## 1. Objective\\nMock Obj\\n\\n## 2. Scope & Implementation Details\\nMock Scope\\n\\n## 3. TDD & Acceptance Criteria\\nMock TDD\\n")
            with open(os.path.join(args.out_dir, "PR_Slice_2.md"), "w") as f:
                f.write("status: open\\n\\n# PR-002: Slice 2\\n\\n## 1. Objective\\nMock Obj\\n\\n## 2. Scope & Implementation Details\\nMock Scope\\n\\n## 3. TDD & Acceptance Criteria\\nMock TDD\\n")
            print('{"status": "mock_success", "role": "planner", "action": "sliced"}')
        else:
            with open(os.path.join(args.out_dir, "PR_A.md"), "w") as f:
                f.write("status: open\\n\\n# PR-001: Feature A\\n\\n## 1. Objective\\nMock Obj\\n\\n## 2. Scope & Implementation Details\\nMock Scope\\n\\n## 3. TDD & Acceptance Criteria\\nMock TDD\\n")
            with open(os.path.join(args.out_dir, "PR_B.md"), "w") as f:
                f.write("status: open\\n\\n# PR-002: Feature B\\n\\n## 1. Objective\\nMock Obj\\n\\n## 2. Scope & Implementation Details\\nMock Scope\\n\\n## 3. TDD & Acceptance Criteria\\nMock TDD\\n")
            print('{"status": "mock_success", "role": "planner"}')
            
        sys.exit(0)
    else:
        import time
        print("Calling OpenClaw real API...")
        session_id = f"subtask-{uuid.uuid4().hex[:8]}"
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="sdlc_prompt_", dir="/tmp", text=True)
        try:
            os.chmod(path, 0o600)
            with os.fdopen(fd, 'w') as tmp:
                tmp.write(task_string)
            
            secure_msg = f"Read your complete task instructions from {path}. Do not modify this file."
            cmd = ["openclaw", "agent", "--session-id", session_id, "-m", secure_msg]
            
            for attempt in range(3):
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print("Successfully spawned Planner subagent.")
                    print(result.stdout)
                    break
                else:
                    print(f"Error: subprocess returned non-zero exit status {result.returncode}")
                    if result.stderr:
                        print(result.stderr)
                    if attempt < 2:
                        sleep_time = 3 * (2 ** attempt)
                        time.sleep(sleep_time)
                    else:
                        sys.exit(1)
        finally:
            if os.path.exists(path):
                os.remove(path)

if __name__ == "__main__":
    main()
