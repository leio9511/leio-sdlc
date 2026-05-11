import os
from typing import Optional

def resolve_global_dir(raw_path: Optional[str]) -> Optional[str]:
    if not raw_path:
        return None
    return os.path.abspath(os.path.expanduser(raw_path))

def get_canonical_job_dir(global_dir: str, workdir: str, prd_file: str) -> str:
    prd_filename = os.path.basename(prd_file)
    base_name, _ = os.path.splitext(prd_filename)
    target_project_name = os.path.basename(os.path.abspath(workdir))
    return os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))
