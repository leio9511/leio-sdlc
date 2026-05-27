import json
import os


EVALUATION_ROLE_BOUNDARY_RULES = [
    "Do not run repository tests.",
    "Do not trigger approval-requiring commands.",
    "If evidence is insufficient, report insufficient evidence instead of executing tests yourself.",
]

ROLE_PROLOGUES = {
    "planner": (
        "You are an Agile Planner. "
        "Your job is to break down large PRDs into granular, sequential PR Contracts "
        "based ONLY on business logic and functional steps."
    ),
    "coder": (
        "You are an autonomous, highly skilled \"Fat Coder\". "
        "You implement features and fix bugs based on the functional requirements "
        "provided in the PR Contract."
    ),
    "reviewer": (
        "You are a Code Audit Logic. "
        "Your mission is to generate a high-fidelity code review report in JSON format."
    ),
    "verifier": (
        "You are an independent, read-only QA Engine (User Acceptance Testing Verifier). "
        "Your sole purpose is to independently verify that every requirement specified in the "
        "provided PRD(s) has been implemented correctly in the final codebase. "
        "You do not write or modify code. You only read, inspect, and report."
    ),
    "auditor": (
        '你是本系统的首席架构师 (Principal Architect)，拥有极高的代码审美和架构洁癖。'
        '你的唯一使命是："绝不让一个定义不清、会引入技术债、违背最佳设计模式的 PRD，'
        '污染我们的代码库。"'
    ),
    "forensic": (
        "You are a site reliability engineer focused on agent fault resolution. "
        "Your job is to analyze failed sessions."
    ),
}

START_WORK_CTA = "As the {role_upper}, begin your task now. Read the reference files first, then proceed."

CODER_RETRY_PREVIOUS_OUTPUT_HEADER = (
    "\n\n## PREVIOUS CODER OUTPUT\n"
    "Your previous execution produced the following output. "
    "Use it as context for this retry. "
    "Do NOT repeat the same mistakes. Address the system alert below.\n\n"
    "{previous_stdout}"
)

CODER_OPERATING_CONSTRAINTS = [
    "DO NOT git push.",
    "DO NOT change git branches.",
    "DO NOT merge into master.",
]

CODER_STARTUP_ASSEMBLY_AUTHORITY_PATH = "scripts/envelope_assembler.py"


def _build_coder_startup_metadata(mode, startup_version, playbook_version, lifecycle=None, prompt_kind=None):
    metadata = {
        "mode": mode,
        "scenario_type": mode,
        "startup_version": startup_version,
        "coder_playbook_version": playbook_version,
        "assembly_authority_path": CODER_STARTUP_ASSEMBLY_AUTHORITY_PATH,
    }
    if lifecycle is not None:
        metadata["lifecycle"] = lifecycle
    if prompt_kind is not None:
        metadata["prompt_kind"] = prompt_kind
    return metadata


def _build_coder_v1_startup_metadata(mode):
    metadata_by_mode = {
        "initial": {
            "lifecycle": "new_session_startup",
            "prompt_kind": "coder_initial_startup",
        },
        "revision_bootstrap": {
            "lifecycle": "recovery_bootstrap_continuation",
            "prompt_kind": "coder_revision_recovery_bootstrap",
        },
        "system_alert_bootstrap": {
            "lifecycle": "recovery_bootstrap_continuation",
            "prompt_kind": "coder_system_alert_recovery_bootstrap",
        },
    }
    selected = metadata_by_mode[mode]
    return _build_coder_startup_metadata(
        mode=mode,
        startup_version="v1",
        playbook_version=1,
        lifecycle=selected["lifecycle"],
        prompt_kind=selected["prompt_kind"],
    )


def _read_text_file(path):
    with open(path, "r") as f:
        return f.read()


def _build_coder_v2_reference_index(references):
    return [
        {
            "id": "pr_contract",
            "kind": "pr_contract",
            "path": references.get("pr_contract_file"),
            "required": True,
            "priority": 1,
            "purpose": "execution_contract_source",
        },
        {
            "id": "prd",
            "kind": "prd",
            "path": references.get("prd_file"),
            "required": True,
            "priority": 1,
            "purpose": "authoritative_requirements",
        },
    ]


def build_coder_v2_envelope(workdir, out_dir, references, contract_params, mode):
    playbook_path = references.get("playbook_path")
    playbook_text = _read_text_file(playbook_path)
    reference_index = _build_coder_v2_reference_index(references)

    if mode == "initial_v2":
        envelope = {
            "role": "coder",
            "mode": "initial",
            "workdir": workdir,
            "mission": "This is the initial new-session coder startup. Start executing the PR contract immediately from the current workspace.",
            "inline_playbook": {
                "path": playbook_path,
                "content": playbook_text,
            },
            "reference_index": reference_index,
            "execution_contract": [f"Locked Working Directory: `{workdir}`"],
            "final_checklist": [],
        }
        envelope.update(
            _build_coder_startup_metadata(
                mode="initial",
                startup_version="v2",
                playbook_version=2,
                lifecycle="new_session_startup",
                prompt_kind="coder_initial_v2_startup",
            )
        )
        return envelope

    current_branch = contract_params.get("current_branch")
    latest_commit_hash = contract_params.get("latest_commit_hash")
    continuation_constraints = [
        f"Locked Working Directory: `{workdir}`",
        "This is not a fresh start.",
        "The existing branch state and on-disk implementation are authoritative.",
    ]
    if current_branch:
        continuation_constraints.append(f"Current branch: `{current_branch}`")
    if latest_commit_hash:
        continuation_constraints.append(f"Latest commit hash: `{latest_commit_hash}`")

    if mode == "revision_bootstrap_v2":
        continuation_constraints.append("The reviewer feedback below is the immediate action target.")
        inline_action_target = {
            "heading": "## REVIEWER FEEDBACK",
            "kind": "reviewer_feedback",
            "path": references.get("feedback_file"),
            "content": _read_text_file(references.get("feedback_file")),
        }
        # Inject previous_output if provided
        if contract_params.get("previous_output"):
            inline_action_target["previous_output"] = contract_params["previous_output"]
        envelope = {
            "role": "coder",
            "mode": "revision_bootstrap",
            "workdir": workdir,
            "mission": "This is a recovery bootstrap for reviewer-driven continuation. This is not a fresh start. Resume from the current branch and the on-disk implementation already present.",
            "inline_playbook": {
                "path": playbook_path,
                "content": playbook_text,
            },
            "reference_index": reference_index,
            "inline_action_target": inline_action_target,
            "continuation_constraints": continuation_constraints,
            "start_instruction": START_WORK_CTA.format(role_upper="CODER"),
        }
        envelope.update(
            _build_coder_startup_metadata(
                mode="revision_bootstrap",
                startup_version="v2",
                playbook_version=2,
                lifecycle="recovery_bootstrap_startup",
                prompt_kind="coder_revision_bootstrap_v2_startup",
            )
        )
        return envelope

    if mode == "system_alert_bootstrap_v2":
        continuation_constraints.append("The system alert below is the immediate corrective target.")
        envelope = {
            "role": "coder",
            "mode": "system_alert_bootstrap",
            "workdir": workdir,
            "mission": "This is a recovery bootstrap for system-alert continuation. This is not a fresh start. Resume from the current branch and the on-disk implementation already present.",
            "inline_playbook": {
                "path": playbook_path,
                "content": playbook_text,
            },
            "reference_index": reference_index,
            "inline_action_target": {
                "heading": "## SYSTEM ALERT",
                "kind": "system_alert",
                "content": contract_params.get("system_alert", ""),
            },
            "continuation_constraints": continuation_constraints,
            "start_instruction": START_WORK_CTA.format(role_upper="CODER"),
        }
        envelope.update(
            _build_coder_startup_metadata(
                mode="system_alert_bootstrap",
                startup_version="v2",
                playbook_version=2,
                lifecycle="recovery_bootstrap_startup",
                prompt_kind="coder_system_alert_bootstrap_v2_startup",
            )
        )
        return envelope

    raise ValueError(f"Unsupported coder v2 mode: {mode}")


def _build_coder_v1_bootstrap_envelope(workdir, references, contract_params, mode):
    envelope = _build_coder_envelope(workdir, references, contract_params, mode)
    envelope.update(
        {
            "workdir": workdir,
            "pr_contract_path": references.get("pr_contract_file"),
            "prd_path": references.get("prd_file"),
            "playbook_path": references.get("playbook_path"),
            "current_branch": contract_params.get("current_branch"),
            "latest_commit_hash": contract_params.get("latest_commit_hash"),
        }
    )

    if mode == "revision_bootstrap":
        envelope.update(
            {
                "feedback_file_path": references.get("feedback_file"),
                "inline_review_json": _read_text_file(references.get("feedback_file")),
                "behavioral_rules": [
                    "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts.",
                ],
                "continuation_semantics": {
                    "fresh_task": False,
                    "existing_branch_state_authoritative": True,
                    "same_session_required": False,
                    "inline_review_section": "# REVIEW REPORT JSON",
                },
            }
        )
        return envelope

    if mode == "system_alert_bootstrap":
        envelope.update(
            {
                "system_alert": contract_params.get("system_alert", ""),
                "behavioral_rules": [
                    "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts.",
                ],
                "continuation_semantics": {
                    "fresh_task": False,
                    "existing_branch_state_authoritative": True,
                    "same_session_required": False,
                    "inline_alert_section": "# SYSTEM ALERT YOU MUST FIX",
                },
            }
        )
        return envelope

    raise ValueError(f"Unsupported coder v1 bootstrap mode: {mode}")


def _append_coder_v1_supporting_context(prompt_lines, envelope):
    prompt_lines.extend(
        [
            "# SUPPORTING CONTEXT",
            f"- Locked workdir: `{envelope.get('workdir', '')}`",
            f"- PR contract path: `{envelope.get('pr_contract_path', '')}`",
            f"- PRD path: `{envelope.get('prd_path', '')}`",
            f"- Coder playbook path: `{envelope.get('playbook_path', '')}`",
        ]
    )
    if envelope.get("feedback_file_path"):
        prompt_lines.append(f"- Feedback file path: `{envelope.get('feedback_file_path')}`")
    if envelope.get("current_branch"):
        prompt_lines.append(f"- Current branch: `{envelope.get('current_branch')}`")
    if envelope.get("latest_commit_hash"):
        prompt_lines.append(f"- Latest commit hash: `{envelope.get('latest_commit_hash')}`")

    prompt_lines.extend(
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


def render_coder_v1_bootstrap_prompt(envelope):
    if envelope.get("mode") == "revision_bootstrap":
        prompt_lines = [
            "# CODER REVISION RECOVERY CONTINUATION",
            "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts.",
            "Prioritize restoring task context from the existing branch and fixing the reviewer findings before rereading supporting references.",
            "The current implementation is authoritative; do not discard or restart the work already present on disk.",
            "",
            "# REVIEW REPORT JSON",
            envelope.get("inline_review_json", ""),
            "",
        ]
        # Inject previous_output if present in the execution_contract
        exec_contract = envelope.get("execution_contract", [])
        for item in exec_contract:
            if isinstance(item, str) and "## PREVIOUS CODER OUTPUT" in item:
                prompt_lines.append(item)
                prompt_lines.append("")
        _append_coder_v1_supporting_context(prompt_lines, envelope)
        return "\n".join(prompt_lines)

    if envelope.get("mode") == "system_alert_bootstrap":
        prompt_lines = [
            "# CODER SYSTEM ALERT RECOVERY CONTINUATION",
            "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts.",
            "The immediate objective is corrective action for the operational failure below, not replanning the PR.",
            "Recover context from the current branch, fix the exact failure, rerun validation, commit if needed, and leave the workspace clean.",
            "",
            "# SYSTEM ALERT YOU MUST FIX",
            envelope.get("system_alert", ""),
            "",
        ]
        _append_coder_v1_supporting_context(prompt_lines, envelope)
        return "\n".join(prompt_lines)

    raise ValueError(f"Unsupported coder v1 bootstrap prompt mode: {envelope.get('mode')}")


def render_coder_v2_prompt(envelope):
    if envelope.get("mode") == "initial":
        prompt_lines = [
            "## IDENTITY & PRIMARY GOAL",
            ROLE_PROLOGUES["coder"],
            "",
            "## MISSION",
            envelope.get("mission", ""),
            "",
            "## CODER PLAYBOOK",
            envelope.get("inline_playbook", {}).get("content", ""),
            "",
            "## REFERENCE INDEX",
            json.dumps(envelope.get("reference_index", []), indent=2),
            "",
            "## WORKSPACE",
            f"- Locked Working Directory: `{envelope.get('workdir', '')}`",
            "",
            "## START WORK",
            START_WORK_CTA.format(role_upper="CODER"),
        ]
        return "\n".join(prompt_lines)

    prompt_lines = [
        "## IDENTITY & PRIMARY GOAL",
        ROLE_PROLOGUES["coder"],
        "",
        "## RECOVERY MISSION",
        envelope.get("mission", ""),
        "",
        "## CODER PLAYBOOK",
        envelope.get("inline_playbook", {}).get("content", ""),
        "",
        "## REFERENCE INDEX",
        json.dumps(envelope.get("reference_index", []), indent=2),
        "",
        envelope.get("inline_action_target", {}).get("heading", "## ACTION TARGET"),
        envelope.get("inline_action_target", {}).get("content", ""),
        "",
    ]
    # Inject previous_output after the action target if present
    previous_output = envelope.get("inline_action_target", {}).get("previous_output")
    if previous_output:
        prompt_lines.extend([
            CODER_RETRY_PREVIOUS_OUTPUT_HEADER.format(previous_stdout=previous_output),
            "",
        ])
    prompt_lines.extend([
        "## CONTINUATION CONSTRAINTS",
    ])
    for constraint in envelope.get("continuation_constraints", []):
        prompt_lines.append(f"- {constraint}")
    prompt_lines.extend(
        [
            "",
            "## START WORK",
            envelope.get("start_instruction", START_WORK_CTA.format(role_upper="CODER")),
        ]
    )
    return "\n".join(prompt_lines)


def _build_planner_envelope(workdir, out_dir, references, contract_params, mode):
    execution_contract = [
        f"The only valid output location for PR contract artifacts in this run is `{out_dir}`.",
        "Any artifact written outside the active output location is invalid for this run.",
        f"You MUST FIRST create each PR contract by calling `{contract_params.get('scaffold_command', '')}` before writing contract content.",
        f"This task is complete only when the generated PR contract files physically exist under `{out_dir}`.",
        "Before producing any artifact, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.",
        "You are explicitly forbidden from manually editing the markdown file's status field.",
        "Follow the PLANNER PLAYBOOK methodologies.",
    ]
    if mode == "uat":
        execution_contract.insert(
            0,
            "Read the required references, then generate focused Micro-PR contracts only for requirements marked missing or partial in the UAT report, without replanning already-satisfied functionality.",
        )
    if mode == "slice" and contract_params.get("failed_pr_id"):
        execution_contract.append(
            f"You MUST use the exact same `--insert-after {contract_params['failed_pr_id']}` value for every sliced PR generated in this run."
        )

    reference_index = [
        {
            "id": "authoritative_prd",
            "kind": "prd",
            "path": references.get("prd_file"),
            "required": True,
            "priority": 1,
            "purpose": "authoritative_requirements",
        },
        {
            "id": "planner_playbook",
            "kind": "playbook",
            "path": references.get("playbook_path"),
            "required": True,
            "priority": 1,
            "purpose": "planner_methodology",
        },
        {
            "id": "pr_contract_template",
            "kind": "template",
            "path": references.get("template_path"),
            "required": True,
            "priority": 1,
            "purpose": "output_contract_shape",
        },
    ]
    if mode == "uat" and references.get("uat_report_path"):
        reference_index.append(
            {
                "id": "uat_report",
                "kind": "uat_report",
                "path": references.get("uat_report_path"),
                "required": True,
                "priority": 1,
                "purpose": "uat_missing_requirements",
            }
        )
    if mode == "slice" and references.get("failed_pr_contract_path"):
        reference_index.append(
            {
                "id": "failed_pr_contract",
                "kind": "pr_contract",
                "path": references.get("failed_pr_contract_path"),
                "required": True,
                "priority": 1,
                "purpose": "failed_slice_boundary_source",
            }
        )

    final_checklist = [
        f"Output path constraint: The only valid output location is `{out_dir}`.",
        f"Scaffold command: MUST use `{contract_params.get('scaffold_command', '')}`.",
        "Exclusivity rule: Any artifact outside the active output location is invalid.",
        f"Done condition: Contracts must physically exist under `{out_dir}`.",
    ]

    return execution_contract, reference_index, final_checklist


def _build_reviewer_envelope(workdir, references, contract_params):
    execution_contract = [
        f"Locked Working Directory: `{workdir}`",
        f"Diff File to review: `{references.get('diff_file')}`",
        f"PR Contract: `{references.get('pr_contract_file')}`",
        f"PRD: `{references.get('prd_file')}`",
        f"Output Report File: `{contract_params.get('output_file')}`",
        f"Output JSON Schema:\n```json\n{json.dumps(contract_params.get('output_schema'), indent=2)}\n```",
        "Mandatory Rule: You MUST read the diff, PR contract, and PRD.",
        "Mandatory Rule: Evaluate only. NEVER modify code or use write tools on the workspace files.",
        "Do not run repository tests.",
        "Do not trigger approval-requiring commands.",
        "If evidence is insufficient, report insufficient evidence instead of executing tests yourself.",
        "You are explicitly forbidden from manually editing the markdown file's status field.",
        "Follow the REVIEWER PLAYBOOK methodologies.",
    ]

    inline_alert = contract_params.get("inline_alert")
    if inline_alert:
        execution_contract.insert(0, inline_alert)

    reference_index = [
        {
            "id": "prd",
            "kind": "prd",
            "path": references.get("prd_file"),
            "required": True,
            "priority": 1,
            "purpose": "requirements",
        },
        {
            "id": "pr_contract",
            "kind": "pr_contract",
            "path": references.get("pr_contract_file"),
            "required": True,
            "priority": 1,
            "purpose": "acceptance_criteria",
        },
        {
            "id": "diff",
            "kind": "diff",
            "path": references.get("diff_file"),
            "required": True,
            "priority": 1,
            "purpose": "code_changes",
        },
        {
            "id": "reviewer_playbook",
            "kind": "playbook",
            "path": references.get("playbook_path"),
            "required": True,
            "priority": 1,
            "purpose": "review_methodology",
        },
    ]

    final_checklist = [
        "Output constraint: Write the JSON review report to the specified file path.",
        "Schema constraint: The output must match the provided JSON schema.",
        "Safety constraint: Do not modify any code files.",
    ]

    return execution_contract, reference_index, final_checklist


def _build_auditor_envelope(workdir, references, contract_params):
    execution_contract = [
        f"Locked Working Directory: `{workdir}`",
        f"PRD to audit: `{references.get('prd_file')}`",
        f"Output Report File: `{contract_params.get('output_file')}`",
        f"Output JSON Schema:\n```json\n{json.dumps(contract_params.get('output_schema'), indent=2)}\n```",
        "Mandatory Rule: You MUST read the PRD before writing the verdict.",
        "Mandatory Rule: Anti-YOLO. Do not rubber-stamp. Follow the playbook.",
    ]

    reference_index = [
        {
            "id": "prd",
            "kind": "prd",
            "path": references.get("prd_file"),
            "required": True,
            "priority": 1,
            "purpose": "requirements_to_audit",
        },
        {
            "id": "auditor_playbook",
            "kind": "playbook",
            "path": references.get("playbook_path"),
            "required": True,
            "priority": 1,
            "purpose": "audit_methodology",
        },
    ]

    final_checklist = [
        "Output constraint: Write the JSON verdict report to the specified file path.",
        "Schema constraint: The output must match the provided JSON schema.",
    ]

    return execution_contract, reference_index, final_checklist


def _split_reference_paths(paths):
    if not paths:
        return []
    if isinstance(paths, str):
        return [path.strip() for path in paths.split(",") if path.strip()]
    return [str(path).strip() for path in paths if str(path).strip()]


def _build_verifier_envelope(workdir, references, contract_params):
    output_file = contract_params.get("output_file")
    output_schema = contract_params.get("output_schema")
    prd_files = _split_reference_paths(references.get("prd_files"))

    execution_contract = [
        f"Locked Working Directory: `{workdir}`",
        f"Output File: `{output_file}`",
        "Read-Only Constraint: You are an evaluation agent. Do NOT modify, create, or delete any workspace files except writing the final UAT JSON output artifact to the exact Output File path.",
        "Before verification, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.",
        *EVALUATION_ROLE_BOUNDARY_RULES,
        f"Output JSON Schema:\n```json\n{json.dumps(output_schema, indent=2)}\n```",
    ]

    reference_index = []
    for idx, prd_file in enumerate(prd_files, start=1):
        reference_index.append(
            {
                "id": f"prd_{idx}",
                "kind": "prd",
                "path": prd_file,
                "required": True,
                "priority": 1,
                "purpose": "requirements_to_verify",
            }
        )

    reference_index.append(
        {
            "id": "verifier_playbook",
            "kind": "playbook",
            "path": references.get("playbook_path"),
            "required": True,
            "priority": 1,
            "purpose": "verification_methodology",
        }
    )

    final_checklist = [
        "Read every required priority-1 reference before beginning verification.",
        f"Read-only constraint: Write only the final UAT JSON output artifact to `{output_file}`.",
        "Schema constraint: The output must match the provided JSON schema.",
    ]

    return execution_contract, reference_index, final_checklist


def _build_coder_envelope(workdir, references, contract_params, mode):
    execution_contract = [
        f"Locked Working Directory: `{workdir}`",
        *CODER_OPERATING_CONSTRAINTS,
        "Git hygiene rule: Use explicit `git add <file>` for only the files you changed. NEVER use `git add .`.",
        "Before coding, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.",
        "Validation rule: Run the relevant tests and `./preflight.sh` if it exists until everything is green.",
        "Completion rule: You must leave the workspace reviewable, commit your changes explicitly, and leave `git status` clean.",
        "Reporting rule: Execute `LATEST_HASH=$(git rev-parse HEAD)` and report the latest commit hash when the task is complete.",
    ]

    if contract_params.get("previous_output"):
        execution_contract.insert(
            4,
            CODER_RETRY_PREVIOUS_OUTPUT_HEADER.format(
                previous_stdout=contract_params["previous_output"]
            ),
        )

    if mode in {"revision", "revision_bootstrap"}:
        execution_contract.insert(6, "Revision work is execution work, not acknowledgment work.")
    if mode == "revision_bootstrap":
        execution_contract.insert(7, "Bootstrap rule: Treat this as a fresh coder session that still must fully execute the reviewer feedback.")

    reference_index = [
        {
            "id": "pr_contract",
            "kind": "pr_contract",
            "path": references.get("pr_contract_file"),
            "required": True,
            "priority": 1,
            "purpose": "execution_contract_source",
        },
        {
            "id": "prd",
            "kind": "prd",
            "path": references.get("prd_file"),
            "required": True,
            "priority": 1,
            "purpose": "authoritative_requirements",
        },
        {
            "id": "coder_playbook",
            "kind": "playbook",
            "path": references.get("playbook_path"),
            "required": True,
            "priority": 1,
            "purpose": "coder_operating_rules",
        },
    ]

    if mode in {"revision", "revision_bootstrap"} and references.get("feedback_file"):
        reference_index.append(
            {
                "id": "reviewer_feedback",
                "kind": "feedback",
                "path": references.get("feedback_file"),
                "required": True,
                "priority": 1,
                "purpose": "actionable_revision_findings",
            }
        )

    final_checklist = [
        "Read every required priority-1 reference before making code changes.",
        "Keep all work inside the locked working directory and preserve branch guardrails.",
        "Run the relevant tests and `./preflight.sh` if it exists until green.",
        "Commit the exact files you changed and leave `git status` clean.",
        "Report the latest commit hash when handing work back.",
    ]

    if mode in {"revision", "revision_bootstrap"}:
        final_checklist.insert(1, "Address the reviewer findings with code changes, not acknowledgment-only output.")

    envelope = {
        "role": "coder",
        "execution_contract": execution_contract,
        "reference_index": reference_index,
        "final_checklist": final_checklist,
    }

    if mode in {"initial", "revision_bootstrap", "system_alert_bootstrap"}:
        envelope.update(_build_coder_v1_startup_metadata(mode))

    return envelope


def build_startup_envelope(role, workdir, out_dir, references, contract_params, mode="standard"):
    if role == "planner":
        execution_contract, reference_index, final_checklist = _build_planner_envelope(
            workdir, out_dir, references, contract_params, mode
        )
    elif role == "reviewer":
        execution_contract, reference_index, final_checklist = _build_reviewer_envelope(
            workdir, references, contract_params
        )
    elif role == "auditor":
        execution_contract, reference_index, final_checklist = _build_auditor_envelope(
            workdir, references, contract_params
        )
    elif role == "verifier":
        execution_contract, reference_index, final_checklist = _build_verifier_envelope(
            workdir, references, contract_params
        )
    elif role == "coder":
        if mode in {"initial_v2", "revision_bootstrap_v2", "system_alert_bootstrap_v2"}:
            return build_coder_v2_envelope(workdir, out_dir, references, contract_params, mode)
        if mode in {"revision_bootstrap", "system_alert_bootstrap"}:
            return _build_coder_v1_bootstrap_envelope(workdir, references, contract_params, mode)
        return _build_coder_envelope(workdir, references, contract_params, mode)
    else:
        execution_contract, reference_index, final_checklist = [], [], []

    return {
        "role": role,
        "execution_contract": execution_contract,
        "reference_index": reference_index,
        "final_checklist": final_checklist,
    }


def render_envelope_to_prompt(envelope):
    if envelope.get("role") == "coder" and envelope.get("startup_version") == "v2":
        return render_coder_v2_prompt(envelope)
    if envelope.get("role") == "coder" and envelope.get("mode") in {"revision_bootstrap", "system_alert_bootstrap"} and envelope.get("startup_version") == "v1":
        return render_coder_v1_bootstrap_prompt(envelope)

    role = envelope.get("role", "agent")
    
    prompt_lines = []
    
    # 1. IDENTITY & PRIMARY GOAL
    prompt_lines.append("## IDENTITY & PRIMARY GOAL")
    prologue = ROLE_PROLOGUES.get(role, f"You are an autonomous {role} agent.")
    prompt_lines.append(prologue)
    prompt_lines.append("")
    
    # Extract constraints
    constraints = []
    contract_clauses = []
    
    for clause in envelope.get("execution_contract", []):
        is_constraint = False
        
        # Check if it's an evaluation role boundary rule
        if role in {"reviewer", "verifier"} and clause in EVALUATION_ROLE_BOUNDARY_RULES:
            is_constraint = True
            
        # Check if it's a coder constraint
        if role == "coder" and clause in CODER_OPERATING_CONSTRAINTS:
            is_constraint = True
            
        # Check for read reference mandate or other mandatory rules
        if "use the read tool to read every reference in the REFERENCE INDEX" in clause:
            is_constraint = True
        elif clause.startswith("Mandatory Rule:"):
            is_constraint = True
            
        if is_constraint:
            constraints.append(clause)
        else:
            contract_clauses.append(clause)
            
    # 2. OPERATING CONSTRAINTS
    prompt_lines.append("## OPERATING CONSTRAINTS")
    for constraint in constraints:
        prompt_lines.append(f"- {constraint}")
    if not constraints:
        prompt_lines.append("- No specific operating constraints for this role.")
    prompt_lines.append("")
        
    # 3. EXECUTION CONTRACT
    prompt_lines.append("## EXECUTION CONTRACT")
    for clause in contract_clauses:
        prompt_lines.append(f"- {clause}")
        
    prompt_lines.append("")
    
    # 4. REFERENCE INDEX
    prompt_lines.append("## REFERENCE INDEX")
    prompt_lines.append(json.dumps(envelope.get("reference_index", []), indent=2))
    
    prompt_lines.append("")
    
    # 5. FINAL CHECKLIST
    prompt_lines.append("## FINAL CHECKLIST")
    for item in envelope.get("final_checklist", []):
        prompt_lines.append(f"- {item}")
        
    prompt_lines.append("")
    
    # 6. START WORK
    prompt_lines.append("## START WORK")
    prompt_lines.append(START_WORK_CTA.format(role_upper=role.upper()))
    
    return "\n".join(prompt_lines)


def save_envelope_artifacts(role, out_dir, envelope, rendered_prompt, extra_artifacts=None, artifact_subdir=None):
    debug_dir = os.path.join(out_dir, f"{role}_debug")
    if artifact_subdir:
        debug_dir = os.path.join(debug_dir, artifact_subdir)
    os.makedirs(debug_dir, exist_ok=True)

    with open(os.path.join(debug_dir, "startup_packet.json"), "w") as f:
        json.dump(envelope, f, indent=2)

    with open(os.path.join(debug_dir, "rendered_prompt.txt"), "w") as f:
        f.write(rendered_prompt)

    if extra_artifacts:
        for filename, content in extra_artifacts.items():
            with open(os.path.join(debug_dir, filename), "w") as f:
                f.write(content)

    return debug_dir
