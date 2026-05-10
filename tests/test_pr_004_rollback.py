import glob
import os
import subprocess
import tarfile
import tempfile

import pytest


def _assert_latest_backup_contains_skill(releases_dir, skill_name):
    backups = sorted(glob.glob(os.path.join(releases_dir, "backup_*.tar.gz")))
    assert backups, f"No backup tarballs found in {releases_dir}"

    latest_backup = backups[-1]
    with tarfile.open(latest_backup, "r:gz") as archive:
        members = archive.getnames()

    assert any(member == skill_name or member.startswith(f"{skill_name}/") for member in members), (
        f"Latest backup {latest_backup} does not contain {skill_name} contents"
    )


def test_independent_symmetrical_rollbacks():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        env["SDLC_RUNTIME_DIR"] = os.path.join(mock_home, "runtime-root-should-be-ignored")

        deploy_script = os.path.join(repo_root, "kit-deploy.sh")
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"First kit-deploy.sh failed: {res.stderr}\n{res.stdout}"

        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Second kit-deploy.sh failed: {res.stderr}\n{res.stdout}"

        skills_dir = os.path.join(mock_home, ".openclaw", "skills")
        releases_root = os.path.join(mock_home, ".openclaw", ".releases")
        for skill in ["leio-sdlc", "pm-skill"]:
            skill_path = os.path.join(skills_dir, skill)
            assert os.path.isdir(skill_path), f"Installed production dir missing for {skill}"

            releases_dir = os.path.join(releases_root, skill)
            assert os.path.isdir(releases_dir), f"Releases dir missing for {skill}"
            _assert_latest_backup_contains_skill(releases_dir, skill)

            marker = os.path.join(skill_path, "MODIFIED_MARKER")
            with open(marker, "w") as f:
                f.write("modified")

        scripts = [
            ("leio-sdlc", os.path.join(repo_root, "scripts", "rollback.sh")),
            ("pm-skill", os.path.join(repo_root, "skills", "pm-skill", "rollback.sh")),
        ]

        for skill_name, script_path in scripts:
            assert os.path.exists(script_path), f"{script_path} does not exist"
            res = subprocess.run(["bash", script_path, "--no-restart"], env=env, cwd=repo_root, capture_output=True, text=True)
            assert res.returncode == 0, (
                f"Rollback failed for {skill_name}:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            )

            skill_path = os.path.join(skills_dir, skill_name)
            marker = os.path.join(skill_path, "MODIFIED_MARKER")
            assert not os.path.exists(marker), f"Rollback did not restore {skill_name} cleanly (marker still exists)"

            if skill_name == "leio-sdlc":
                assert os.path.exists(os.path.join(skill_path, "scripts", "orchestrator.py"))
            elif skill_name == "pm-skill":
                assert os.path.exists(os.path.join(skill_path, "scripts", "init_prd.py"))


def test_rollback_no_restart_with_mock():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        env["SDLC_RUNTIME_DIR"] = os.path.join(mock_home, "runtime-root-should-be-ignored")

        deploy_script = os.path.join(repo_root, "kit-deploy.sh")
        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"kit-deploy.sh failed: {res.stderr}\n{res.stdout}"

        res = subprocess.run(["bash", deploy_script], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Second kit-deploy.sh failed: {res.stderr}\n{res.stdout}"

        script_path = os.path.join(repo_root, "scripts", "rollback.sh")
        res = subprocess.run(["bash", script_path], env=env, cwd=repo_root, capture_output=True, text=True)
        assert res.returncode == 0, f"Rollback failed: {res.stderr}\n{res.stdout}"

        assert "Skipping OpenClaw gateway restart (mock environment detected)..." in res.stdout, (
            "Gateway restart was not skipped"
        )


def test_rollback_lock_guardrails():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with tempfile.TemporaryDirectory() as mock_home:
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        env["SDLC_RUNTIME_DIR"] = os.path.join(mock_home, "runtime-root-should-be-ignored")

        skills_dir = os.path.join(mock_home, ".openclaw", "skills")
        os.makedirs(skills_dir, exist_ok=True)
        leio_sdlc_dir = os.path.join(skills_dir, "leio-sdlc")
        os.makedirs(leio_sdlc_dir, exist_ok=True)

        releases_dir = os.path.join(mock_home, ".openclaw", ".releases", "leio-sdlc")
        os.makedirs(releases_dir, exist_ok=True)
        subprocess.run(
            ["tar", "-czf", os.path.join(releases_dir, "backup_20230101_000000.tar.gz"), "-C", skills_dir, "leio-sdlc"],
            check=True,
        )

        rollback_script = os.path.join(repo_root, "scripts", "rollback.sh")

        for lock_file in [".sdlc_repo.lock", ".coder_session", ".sdlc_lock_manifest.json"]:
            lock_path = os.path.join(leio_sdlc_dir, lock_file)
            with open(lock_path, "w") as f:
                f.write("locked")

            res = subprocess.run(["bash", rollback_script, "--no-restart"], env=env, cwd=leio_sdlc_dir, capture_output=True, text=True)
            assert res.returncode != 0, f"Rollback should have failed due to {lock_file}"
            assert "[FATAL_LOCK] Cannot rollback while another SDLC pipeline is active" in res.stdout

            os.remove(lock_path)
