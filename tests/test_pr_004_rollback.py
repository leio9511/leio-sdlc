import os
import subprocess

from openclaw_mock_support import provision_fake_openclaw
from deploy_test_support import (
    ROOT_SKILL_SLUG,
    assert_isolated_checkout,
    canonical_openclaw_home,
    canonical_releases_dir,
    canonical_skill_dir,
    isolated_repo_env,
)


PM_SLUG = "pm-skill"
MODIFIED_MARKER = "MODIFIED_MARKER"
LOCK_FILES = (".sdlc_repo.lock", ".coder_session", ".sdlc_lock_manifest.json")


def _run(command: list[str], *, env: dict[str, str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True)


def test_independent_symmetrical_rollbacks():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with isolated_repo_env(repo_root) as isolated:
        isolated_root = isolated["repo_root"]
        mock_home = isolated["mock_home"]
        env = isolated["env"]

        assert_isolated_checkout(isolated_root)
        assert env["HOME_MOCK"] == mock_home

        deploy_script = os.path.join(isolated_root, "kit-deploy.sh")
        root_rollback = os.path.join(isolated_root, "scripts", "rollback.sh")
        pm_rollback = os.path.join(isolated_root, "skills", "pm-skill", "rollback.sh")

        first = _run(["bash", deploy_script], env=env, cwd=isolated_root)
        assert first.returncode == 0, f"First kit-deploy.sh failed:\nSTDOUT: {first.stdout}\nSTDERR: {first.stderr}"

        second = _run(["bash", deploy_script], env=env, cwd=isolated_root)
        assert second.returncode == 0, f"Second kit-deploy.sh failed:\nSTDOUT: {second.stdout}\nSTDERR: {second.stderr}"

        for slug in (ROOT_SKILL_SLUG, PM_SLUG):
            releases_dir = canonical_releases_dir(mock_home, slug)
            skill_dir = canonical_skill_dir(mock_home, slug)
            assert os.path.isdir(releases_dir), f"Releases dir missing for {slug}: {releases_dir}"
            assert any(name.startswith("backup_") and name.endswith(".tar.gz") for name in os.listdir(releases_dir))
            marker = os.path.join(skill_dir, MODIFIED_MARKER)
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("modified")
            assert os.path.exists(marker)

        root_result = _run(["bash", root_rollback, "--no-restart"], env=env, cwd=isolated_root)
        assert root_result.returncode == 0, (
            f"Rollback failed for {ROOT_SKILL_SLUG}:\nSTDOUT: {root_result.stdout}\nSTDERR: {root_result.stderr}"
        )

        pm_result = _run(["bash", pm_rollback, "--no-restart"], env=env, cwd=isolated_root)
        assert pm_result.returncode == 0, (
            f"Rollback failed for {PM_SLUG}:\nSTDOUT: {pm_result.stdout}\nSTDERR: {pm_result.stderr}"
        )

        root_skill_dir = canonical_skill_dir(mock_home, ROOT_SKILL_SLUG)
        pm_skill_dir = canonical_skill_dir(mock_home, PM_SLUG)
        assert not os.path.exists(os.path.join(root_skill_dir, MODIFIED_MARKER))
        assert not os.path.exists(os.path.join(pm_skill_dir, MODIFIED_MARKER))
        assert os.path.exists(os.path.join(root_skill_dir, "scripts", "orchestrator.py"))
        assert os.path.exists(os.path.join(pm_skill_dir, "scripts", "init_prd.py"))


def test_rollback_no_restart_with_mock():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with isolated_repo_env(repo_root) as isolated:
        isolated_root = isolated["repo_root"]
        mock_home = isolated["mock_home"]
        env = isolated["env"]

        assert_isolated_checkout(isolated_root)

        deploy_script = os.path.join(isolated_root, "kit-deploy.sh")
        root_rollback = os.path.join(isolated_root, "scripts", "rollback.sh")

        with provision_fake_openclaw() as (temp_bin, get_calls):
            # Prepend to the isolated env PATH
            original_path = env.get("PATH", "")
            env["PATH"] = f"{temp_bin}:{original_path}"
            
            first = _run(["bash", deploy_script], env=env, cwd=isolated_root)
            assert first.returncode == 0, f"First kit-deploy.sh failed:\nSTDOUT: {first.stdout}\nSTDERR: {first.stderr}"

            second = _run(["bash", deploy_script], env=env, cwd=isolated_root)
            assert second.returncode == 0, f"Second kit-deploy.sh failed:\nSTDOUT: {second.stdout}\nSTDERR: {second.stderr}"

            marker = os.path.join(canonical_skill_dir(mock_home, ROOT_SKILL_SLUG), MODIFIED_MARKER)
            with open(marker, "w", encoding="utf-8") as handle:
                handle.write("modified")

            result = _run(["bash", root_rollback], env=env, cwd=isolated_root)
            assert result.returncode == 0, f"Rollback failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            assert "Skipping OpenClaw gateway restart (mock environment detected)..." in result.stdout
            assert not os.path.exists(marker)



def test_rollback_lock_guardrails():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with isolated_repo_env(repo_root) as isolated:
        isolated_root = isolated["repo_root"]
        mock_home = isolated["mock_home"]
        env = isolated["env"]

        assert_isolated_checkout(isolated_root)

        deploy_script = os.path.join(isolated_root, "deploy.sh")
        rollback_script = os.path.join(isolated_root, "scripts", "rollback.sh")

        first = _run(["bash", deploy_script, "--no-restart"], env=env, cwd=isolated_root)
        assert first.returncode == 0, f"First deploy failed:\nSTDOUT: {first.stdout}\nSTDERR: {first.stderr}"

        second = _run(["bash", deploy_script, "--no-restart"], env=env, cwd=isolated_root)
        assert second.returncode == 0, f"Second deploy failed:\nSTDOUT: {second.stdout}\nSTDERR: {second.stderr}"

        prod_dir = canonical_skill_dir(mock_home, ROOT_SKILL_SLUG)
        for lock_file in LOCK_FILES:
            lock_path = os.path.join(prod_dir, lock_file)
            with open(lock_path, "w", encoding="utf-8") as handle:
                handle.write("locked")

            result = _run(["bash", rollback_script, "--no-restart"], env=env, cwd=isolated_root)
            assert result.returncode != 0, f"Rollback should have failed due to {lock_file}"
            assert "[FATAL_LOCK] Cannot rollback while another SDLC pipeline is active" in result.stdout

            os.remove(lock_path)


def test_rollback_reports_missing_backup_tarballs_for_root_and_pm_skill():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    with isolated_repo_env(repo_root) as isolated:
        isolated_root = isolated["repo_root"]
        mock_home = isolated["mock_home"]
        env = isolated["env"]

        assert_isolated_checkout(isolated_root)

        openclaw_home = canonical_openclaw_home(mock_home)
        for slug, rollback_script in (
            (ROOT_SKILL_SLUG, os.path.join(isolated_root, "scripts", "rollback.sh")),
            (PM_SLUG, os.path.join(isolated_root, "skills", "pm-skill", "rollback.sh")),
        ):
            releases_dir = canonical_releases_dir(mock_home, slug)
            os.makedirs(releases_dir, exist_ok=True)

            result = _run(["bash", rollback_script, "--no-restart"], env=env, cwd=isolated_root)
            assert result.returncode != 0
            assert f"No backup tarballs found in {releases_dir}" in result.stdout
            assert result.stderr == ""
            assert os.path.isdir(openclaw_home)
