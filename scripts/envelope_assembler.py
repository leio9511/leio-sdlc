import json
import os


def _build_planner_envelope(workdir, out_dir, references, contract_params, mode):
    execution_contract = [
        f"The only valid output location for PR contract artifacts in this run is `{out_dir}`.",
        "Any artifact written outside the active output location is invalid for this run.",
        f"You MUST FIRST create each PR contract by calling `{contract_params.get('scaffold_command', '')}` before writing contract content.",
        f"This task is complete only when the generated PR contract files physically exist under `{out_dir}`.",
        "Before producing any artifact, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.",
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
    ]

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


def _build_coder_envelope(workdir, references, contract_params, mode):
    execution_contract = [
        f"Locked Working Directory: `{workdir}`",
        "Branch isolation rule: Stay on the current feature branch. NEVER switch branches and NEVER work on `master` or `main`.",
        "Push rule: DO NOT `git push`.",
        "Git hygiene rule: Use explicit `git add <file>` for only the files you changed. NEVER use `git add .`.",
        "Before coding, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1.",
        "Validation rule: Run the relevant tests and `./preflight.sh` if it exists until everything is green.",
        "Completion rule: You must leave the workspace reviewable, commit your changes explicitly, and leave `git status` clean.",
        "Reporting rule: Execute `LATEST_HASH=$(git rev-parse HEAD)` and report the latest commit hash when the task is complete.",
    ]

    if mode in {"revision", "revision_bootstrap"}:
        execution_contract.insert(5, "Revision work is execution work, not acknowledgment work.")
    if mode == "revision_bootstrap":
        execution_contract.insert(6, "Bootstrap rule: Treat this as a fresh coder session that still must fully execute the reviewer feedback.")
    if mode == "system_alert" and contract_params.get("system_alert"):
        execution_contract.insert(5, f"System alert requiring corrective action: {contract_params['system_alert']}")

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

    if mode == "system_alert":
        final_checklist.insert(1, "Resolve the corrective-action alert completely, not just conversationally.")
    elif mode in {"revision", "revision_bootstrap"}:
        final_checklist.insert(1, "Address the reviewer findings with code changes, not acknowledgment-only output.")

    return execution_contract, reference_index, final_checklist


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
    elif role == "coder":
        execution_contract, reference_index, final_checklist = _build_coder_envelope(
            workdir, references, contract_params, mode
        )
    else:
        execution_contract, reference_index, final_checklist = [], [], []

    return {
        "role": role,
        "execution_contract": execution_contract,
        "reference_index": reference_index,
        "final_checklist": final_checklist,
    }


def render_envelope_to_prompt(envelope):
    prompt_lines = ["# EXECUTION CONTRACT"]
    for clause in envelope.get("execution_contract", []):
        prompt_lines.append(f"- {clause}")

    prompt_lines.append("")
    prompt_lines.append("# REFERENCE INDEX")
    prompt_lines.append(json.dumps(envelope.get("reference_index", []), indent=2))

    prompt_lines.append("")
    prompt_lines.append("# FINAL CHECKLIST")
    for item in envelope.get("final_checklist", []):
        prompt_lines.append(f"- {item}")

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
