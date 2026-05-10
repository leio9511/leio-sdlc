import glob
import os
import subprocess
import unittest

from deploy_test_support import isolated_repo_env


class TestDeployBackup(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_sdlc_deploy_creates_backup(self):
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            self.assertNotEqual(os.path.basename(repo_root), "leio-sdlc")
            self.assertEqual(env["HOME_MOCK"], mock_home)
            self.assertFalse(os.path.exists(os.path.join(mock_home, ".openclaw", "skills", "leio-sdlc")))
            self.assertFalse(os.path.exists(os.path.join(mock_home, ".openclaw", ".releases", "leio-sdlc")))

            deploy_script = os.path.join(repo_root, "deploy.sh")
            prod_dir = os.path.join(mock_home, ".openclaw", "skills", "leio-sdlc")

            res1 = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res1.returncode, 0, f"First deploy failed: {res1.stderr}\n{res1.stdout}")
            self.assertTrue(os.path.exists(prod_dir), "Prod dir not created for leio-sdlc")
            self.assertTrue(
                os.path.exists(os.path.join(prod_dir, "scripts", "orchestrator.py")),
                "orchestrator.py not deployed into canonical prod dir",
            )

            res2 = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res2.returncode, 0, f"Second deploy failed: {res2.stderr}\n{res2.stdout}")

            releases_dir = os.path.join(mock_home, ".openclaw", ".releases", "leio-sdlc")
            self.assertTrue(os.path.exists(releases_dir), "Releases dir not created for leio-sdlc")

            backups = glob.glob(os.path.join(releases_dir, "backup_*.tar.gz"))
            self.assertTrue(len(backups) >= 1, "Backup tar.gz file not found after second deployment for leio-sdlc")

    def test_pm_skill_deploy_creates_backup(self):
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            self.assertNotEqual(os.path.basename(repo_root), "leio-sdlc")
            self.assertEqual(env["HOME_MOCK"], mock_home)
            self.assertFalse(os.path.exists(os.path.join(mock_home, ".openclaw", "skills", "pm-skill")))
            self.assertFalse(os.path.exists(os.path.join(mock_home, ".openclaw", ".releases", "pm-skill")))

            deploy_script = os.path.join(repo_root, "skills", "pm-skill", "deploy.sh")
            prod_dir = os.path.join(mock_home, ".openclaw", "skills", "pm-skill")

            res1 = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=mock_home,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res1.returncode, 0, f"First deploy failed: {res1.stderr}\n{res1.stdout}")
            self.assertTrue(os.path.exists(prod_dir), "Prod dir not created for pm-skill")
            self.assertTrue(
                os.path.exists(os.path.join(prod_dir, "scripts", "agent_driver.py")),
                "agent_driver.py not bundled properly",
            )

            res2 = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=os.path.dirname(deploy_script),
                capture_output=True,
                text=True,
            )
            self.assertEqual(res2.returncode, 0, f"Second deploy failed: {res2.stderr}\n{res2.stdout}")

            releases_dir = os.path.join(mock_home, ".openclaw", ".releases", "pm-skill")
            self.assertTrue(os.path.exists(releases_dir), "Releases dir not created for pm-skill")

            backups = glob.glob(os.path.join(releases_dir, "backup_*.tar.gz"))
            self.assertTrue(len(backups) >= 1, "Backup tar.gz file not found after second deployment for pm-skill")
