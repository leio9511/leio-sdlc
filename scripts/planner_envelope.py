import json
import os

def build_planner_envelope(workdir, out_dir, prd_path, playbook_path, template_path, mode="standard", uat_report_path=None, failed_pr_id=None):
    contract_script = "/root/.openclaw/skills/leio-sdlc/scripts/create_pr_contract.py"
    
    execution_contract_lines = [
        f"The only valid output location for PR contract artifacts in this run is `{out_dir}`.",
        "Any artifact written outside the active output location is invalid for this run.",
        f"You MUST FIRST create each PR contract by calling `python3 {contract_script} --only-scaffold --workdir {workdir} --job-dir {out_dir} --title <title>` before writing contract content.",
        f"This task is complete only when the generated PR contract files physically exist under `{out_dir}`.",
        "Before producing any artifact, you MUST use the read tool to read every reference in the REFERENCE INDEX where required=true and priority=1."
    ]

    if mode == "uat":
        execution_contract_lines.insert(0, "Read the required references, then generate focused Micro-PR contracts only for requirements marked missing or partial in the UAT report, without replanning already-satisfied functionality.")
    
    if mode == "slice" and failed_pr_id:
        execution_contract_lines.append(f"You MUST use the exact same `--insert-after {failed_pr_id}` value for every sliced PR generated in this run.")

    reference_index = [
        {
            "id": "authoritative_prd",
            "kind": "prd",
            "path": prd_path,
            "required": True,
            "priority": 1,
            "purpose": "authoritative_requirements"
        },
        {
            "id": "planner_playbook",
            "kind": "playbook",
            "path": playbook_path,
            "required": True,
            "priority": 1,
            "purpose": "planner_methodology"
        },
        {
            "id": "pr_contract_template",
            "kind": "template",
            "path": template_path,
            "required": True,
            "priority": 1,
            "purpose": "output_contract_shape"
        }
    ]

    if mode == "uat" and uat_report_path:
        reference_index.append({
            "id": "uat_report",
            "kind": "uat_report",
            "path": uat_report_path,
            "required": True,
            "priority": 1,
            "purpose": "uat_missing_requirements"
        })

    final_checklist_lines = [
        f"Output path constraint: The only valid output location is `{out_dir}`.",
        f"Scaffold command: MUST use `python3 {contract_script} --only-scaffold --workdir {workdir} --job-dir {out_dir} --title <title>`.",
        "Exclusivity rule: Any artifact outside the active output location is invalid.",
        f"Done condition: Contracts must physically exist under `{out_dir}`."
    ]

    return {
        "execution_contract": execution_contract_lines,
        "reference_index": reference_index,
        "final_checklist": final_checklist_lines
    }

def save_debug_artifacts(out_dir, envelope_dict, rendered_prompt, scaffold_command):
    debug_dir = os.path.join(out_dir, "planner_debug")
    os.makedirs(debug_dir, exist_ok=True)
    
    with open(os.path.join(debug_dir, "startup_packet.json"), "w") as f:
        json.dump(envelope_dict, f, indent=2)
        
    with open(os.path.join(debug_dir, "startup_prompt.txt"), "w") as f:
        f.write(rendered_prompt)
        
    with open(os.path.join(debug_dir, "scaffold_contract.txt"), "w") as f:
        f.write(scaffold_command)

def render_planner_prompt(envelope: dict) -> str:
    prompt_lines = []
    
    prompt_lines.append("# EXECUTION CONTRACT")
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
