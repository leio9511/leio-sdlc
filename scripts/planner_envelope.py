# planner_envelope.py — backward-compatible adapter
from envelope_assembler import build_startup_envelope, render_envelope_to_prompt, save_envelope_artifacts

def build_planner_envelope(
    workdir,
    out_dir,
    prd_path,
    playbook_path,
    template_path,
    contract_script,
    mode="standard",
    uat_report_path=None,
    failed_pr_id=None,
    failed_pr_contract_path=None,
):
    references = {
        "prd_file": prd_path,
        "playbook_path": playbook_path,
        "template_path": template_path
    }
    if uat_report_path:
        references["uat_report_path"] = uat_report_path
    if failed_pr_contract_path:
        references["failed_pr_contract_path"] = failed_pr_contract_path
        
    contract_params = {
        "scaffold_command": f"python3 {contract_script} --only-scaffold --workdir {workdir} --job-dir {out_dir} --title <title>"
    }
    if failed_pr_id:
        contract_params["failed_pr_id"] = failed_pr_id
        
    return build_startup_envelope(
        role="planner",
        workdir=workdir,
        out_dir=out_dir,
        references=references,
        contract_params=contract_params,
        mode=mode
    )

def render_planner_prompt(envelope: dict) -> str:
    return render_envelope_to_prompt(envelope)

def save_debug_artifacts(out_dir, envelope_dict, rendered_prompt, scaffold_command):
    # preserve old artifact filenames and behavior exactly
    save_envelope_artifacts(
        role="planner",
        out_dir=out_dir,
        envelope=envelope_dict,
        rendered_prompt=rendered_prompt,
        extra_artifacts={
            "startup_prompt.txt": rendered_prompt,
            "scaffold_contract.txt": scaffold_command,
        },
    )
