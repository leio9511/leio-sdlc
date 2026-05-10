"""Helpers for seeding planner-success artifacts in orchestrator tests."""

import os
from typing import Dict, List


DEFAULT_PR_SLICE_NAME = "PR_001_test.md"
DEFAULT_PR_SLICE_CONTENT = "status: open\n"


def compute_orchestrator_job_dir(workdir: str, global_dir: str, prd_filename: str = "dummy_prd.md") -> str:
    """Return the job_dir path the orchestrator computes for a PRD run."""
    target_project_name = os.path.basename(os.path.abspath(workdir))
    base_name, _ = os.path.splitext(os.path.basename(prd_filename))
    return os.path.abspath(
        os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name)
    )


def seed_planner_success_artifacts(
    workdir: str,
    global_dir: str,
    prd_filename: str = "dummy_prd.md",
    pr_slice_name: str = DEFAULT_PR_SLICE_NAME,
    pr_slice_content: str = DEFAULT_PR_SLICE_CONTENT,
) -> Dict[str, object]:
    """Create the minimal planner-success filesystem contract for tests.

    The real orchestrator requires a job_dir under:
      <global_dir>/.sdlc_runs/<project_name>/<prd_name_without_ext>

    and at least one discoverable markdown PR slice inside that directory.
    """
    job_dir = compute_orchestrator_job_dir(workdir, global_dir, prd_filename)
    os.makedirs(job_dir, exist_ok=True)

    pr_file = os.path.join(job_dir, pr_slice_name)
    with open(pr_file, "w", encoding="utf-8") as handle:
        handle.write(pr_slice_content)

    md_files: List[str] = [pr_file]
    return {
        "job_dir": job_dir,
        "pr_file": pr_file,
        "md_files": md_files,
    }
