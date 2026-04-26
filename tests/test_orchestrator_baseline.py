import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import orchestrator


# ---------------------------------------------------------------------------
# Test Case 1: baseline_commit.txt and run_manifest.json are created BEFORE
#              spawn_planner.py is invoked
# ---------------------------------------------------------------------------
def test_baseline_created_before_planner():
    """
    Given the orchestrator has resolved job_dir and run_dir
    When spawn_planner.py has not yet been invoked
    Then baseline_commit.txt exists in job_dir containing the current HEAD commit hash
    And run_manifest.json exists in run_dir containing keys:
        baseline_commit, prd_path, job_dir, run_dir, started_at
    """
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        prd_file = os.path.join(td, "dummy_prd.md")
        with open(prd_file, "w") as f:
            f.write("# Dummy PRD")

        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name = os.path.splitext(os.path.basename(prd_file))[0]
        job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))

        planner_was_called = {"called": False}

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "abc123def456789012345678901234567890abcd\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                res.stdout = "master\n"
            return res

        def fake_dpopen(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "spawn_planner.py" in cmd_str:
                planner_was_called["called"] = True
                # Simulate Planner creating PR files
                os.makedirs(job_dir, exist_ok=True)
                with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
                    f.write("dummy PR")
                proc = MagicMock()
                proc.returncode = 0
                return proc
            raise KeyboardInterrupt("Stop orchestrator loop")

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--force-replan", "true",
            "--enable-exec-from-workspace",
            "--channel", "slack:C123"
        ]

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), \
             patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except (KeyboardInterrupt, SystemExit):
                pass

        # Assert baseline_commit.txt exists and contains the correct hash
        baseline_file = os.path.join(job_dir, "baseline_commit.txt")
        assert os.path.exists(baseline_file), (
            "baseline_commit.txt must exist BEFORE Planner execution"
        )
        with open(baseline_file, "r") as f:
            content = f.read().strip()
        assert content == "abc123def456789012345678901234567890abcd", (
            f"Expected mocked hash, got: {content}"
        )

        # Assert run_manifest.json exists with correct keys
        manifest_path = os.path.join(job_dir, "run_manifest.json")
        assert os.path.exists(manifest_path), (
            "run_manifest.json must exist in run_dir"
        )
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        required_keys = {"baseline_commit", "prd_path", "job_dir", "run_dir", "started_at"}
        assert required_keys.issubset(set(manifest.keys())), (
            f"run_manifest.json missing keys: {required_keys - set(manifest.keys())}"
        )
        assert manifest["baseline_commit"] == "abc123def456789012345678901234567890abcd"
        assert manifest["prd_path"] == os.path.abspath(prd_file)
        assert manifest["job_dir"] == job_dir
        assert manifest["run_dir"] == job_dir


# ---------------------------------------------------------------------------
# Test Case 2: orchestrator with --resume detects existing anchors and
#              resumes execution instead of exiting with FATAL_METADATA
# ---------------------------------------------------------------------------
def test_resume_works_after_slicing_crash():
    """
    Given baseline_commit.txt and run_manifest.json exist in job_dir from a
    previous run
    When the orchestrator is invoked with force_replan=false (--resume scenario)
    Then the orchestrator detects existing anchors and resumes execution
    And does NOT exit with [FATAL_METADATA] Critical SDLC anchors are missing
    """
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        prd_file = os.path.join(td, "dummy_prd.md")
        with open(prd_file, "w") as f:
            f.write("# Dummy PRD")

        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name = os.path.splitext(os.path.basename(prd_file))[0]
        job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))

        # Pre-seed job_dir with existing anchors (simulating a crashed previous run)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "baseline_commit.txt"), "w") as f:
            f.write("existing_hash_99999")
        with open(os.path.join(job_dir, "run_manifest.json"), "w") as f:
            json.dump({
                "baseline_commit": "existing_hash_99999",
                "prd_path": os.path.abspath(prd_file),
                "job_dir": job_dir,
                "run_dir": job_dir,
                "started_at": "2025-01-01T00:00:00+00:00"
            }, f)

        # Also seed PR files so the resume path detects them (simulating Planner
        # successfully sliced before the simulated crash)
        with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
            f.write("dummy PR")

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--force-replan", "false",
            "--enable-exec-from-workspace",
            "--channel", "slack:C123"
        ]

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "existing_hash_99999\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                res.stdout = "master\n"
            return res

        # dpopen should NOT be called for spawn_planner in resume mode
        # (existing PRs detected, no new slicing needed)
        planner_called_on_resume = {"called": False}

        def fake_dpopen(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "spawn_planner.py" in cmd_str:
                planner_called_on_resume["called"] = True
            raise KeyboardInterrupt("Stop orchestrator loop")

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), \
             patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except (KeyboardInterrupt, SystemExit):
                pass

        # The key assertion: existing anchors (baseline + manifest) remain untouched
        assert os.path.exists(os.path.join(job_dir, "baseline_commit.txt")), (
            "baseline_commit.txt must persist through resume"
        )
        assert os.path.exists(os.path.join(job_dir, "run_manifest.json")), (
            "run_manifest.json must persist through resume"
        )

        # Verify baseline file was NOT overwritten on resume
        with open(os.path.join(job_dir, "baseline_commit.txt"), "r") as f:
            assert f.read().strip() == "existing_hash_99999", (
                "Existing baseline must not be overwritten during resume"
            )

        # Planner should NOT have been re-invoked (resume path, not fresh slicing)
        assert not planner_called_on_resume["called"], (
            "spawn_planner.py must not be called during resume with existing PRs"
        )


# ---------------------------------------------------------------------------
# Test Case 3: run_manifest.json schema validation
# ---------------------------------------------------------------------------
def test_manifest_json_schema():
    """
    Given the orchestrator creates run_manifest.json
    When the file is parsed
    Then it contains valid JSON with exactly the required keys
    And started_at is a valid ISO 8601 timestamp
    And baseline_commit is a 40-character hex string
    """
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        prd_file = os.path.join(td, "dummy_prd.md")
        with open(prd_file, "w") as f:
            f.write("# Dummy PRD")

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--force-replan", "true",
            "--enable-exec-from-workspace",
            "--channel", "slack:C123"
        ]

        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name = os.path.splitext(os.path.basename(prd_file))[0]
        job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "deadbeef0123456789abcdef9876543210fedcba\n"
            elif isinstance(cmd, list) and "branch" in cmd:
                res.stdout = "master\n"
            return res

        def fake_dpopen(cmd, *args, **kwargs):
            if "spawn_planner.py" in str(cmd):
                os.makedirs(job_dir, exist_ok=True)
                with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
                    f.write("dummy PR")
                proc = MagicMock()
                proc.returncode = 0
                return proc
            raise KeyboardInterrupt("Stop orchestrator loop")

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), \
             patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except (KeyboardInterrupt, SystemExit):
                pass

        manifest_path = os.path.join(job_dir, "run_manifest.json")
        assert os.path.exists(manifest_path), "run_manifest.json must be created"

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Schema: exact required keys
        required_keys = {"baseline_commit", "prd_path", "job_dir", "run_dir", "started_at"}
        assert set(manifest.keys()) == required_keys, (
            f"run_manifest.json must contain exactly {required_keys}, got {set(manifest.keys())}"
        )

        # baseline_commit must be a 40-char hex string
        bc = manifest["baseline_commit"]
        assert isinstance(bc, str), "baseline_commit must be a string"
        assert len(bc) == 40, f"baseline_commit must be 40 chars, got {len(bc)}: {bc}"
        assert all(c in "0123456789abcdef" for c in bc), (
            f"baseline_commit must be hex, got: {bc}"
        )

        # started_at must be a valid ISO 8601 timestamp
        started = manifest["started_at"]
        assert isinstance(started, str), "started_at must be a string"
        # ISO 8601: must contain 'T' and either '+' or 'Z' offset
        assert "T" in started, f"started_at must be ISO 8601, got: {started}"
        assert started.endswith("Z") or "+" in started.split("T")[-1], (
            f"started_at must have timezone offset, got: {started}"
        )
        # Ensure it parses as a valid datetime
        try:
            datetime.fromisoformat(started)
        except ValueError as e:
            pytest.fail(f"started_at is not a valid ISO 8601 datetime: {started} ({e})")

        # prd_path must be an absolute path
        assert os.path.isabs(manifest["prd_path"]), (
            f"prd_path must be absolute, got: {manifest['prd_path']}"
        )

        # job_dir and run_dir must be the same absolute path
        assert manifest["job_dir"] == manifest["run_dir"], (
            "job_dir and run_dir must be identical"
        )


# ---------------------------------------------------------------------------
# Legacy: ensure existing baseline file is not overwritten
# ---------------------------------------------------------------------------
def test_orchestrator_does_not_overwrite_existing_baseline():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        global_dir = os.path.join(td, "global")
        os.makedirs(workdir)
        os.makedirs(os.path.join(workdir, ".git"))
        os.makedirs(global_dir)
        prd_file = os.path.join(td, "dummy.md")
        with open(prd_file, "w") as f:
            f.write("dummy")

        target_project_name = os.path.basename(os.path.abspath(workdir))
        job_dir = os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, "dummy"))
        os.makedirs(job_dir)

        baseline_file = os.path.join(job_dir, "baseline_commit.txt")
        with open(baseline_file, "w") as f:
            f.write("existing_hash_99999")

        with open(os.path.join(job_dir, "PR_001.md"), "w") as f:
            f.write("dummy")

        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", prd_file,
            "--force-replan", "false", "--enable-exec-from-workspace",
            "--channel", "slack:C123"
        ]

        def fake_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            if cmd == ["git", "rev-parse", "HEAD"]:
                res.stdout = "new_hash_11111\n"
            elif "branch" in cmd:
                res.stdout = "master\n"
            return res

        def fake_dpopen(cmd, *args, **kwargs):
            if "spawn_planner.py" in str(cmd):
                proc = MagicMock()
                proc.returncode = 0
                return proc
            raise KeyboardInterrupt("Stop orchestrator loop")

        with patch("sys.argv", test_args), \
             patch("subprocess.run", side_effect=fake_subprocess_run), \
             patch("orchestrator.dpopen", side_effect=fake_dpopen), \
             patch("orchestrator.notify_channel"), patch("git_utils.check_git_boundary"):
            try:
                orchestrator.main()
            except (KeyboardInterrupt, SystemExit):
                pass

            assert os.path.exists(baseline_file)
            with open(baseline_file, "r") as f:
                content = f.read()
            assert content.strip() == "existing_hash_99999", (
                "Existing baseline file should not be overwritten"
            )
