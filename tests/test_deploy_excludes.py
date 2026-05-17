import os
import subprocess
import unittest

from deploy_test_support import install_fake_python_toolchain, isolated_repo_env


class TestDeployExcludes(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_deploy_excludes_tests(self):
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            deploy_script = os.path.join(repo_root, "deploy.sh")
            install_fake_python_toolchain(repo_root, env)
            res = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Deploy failed: {res.stderr}\n{res.stdout}")

            prod_dir = os.path.join(mock_home, ".openclaw", "skills", "leio-sdlc")
            self.assertTrue(os.path.exists(prod_dir), "Prod dir not created")
            self.assertFalse(os.path.exists(os.path.join(prod_dir, "tests")), "tests/ directory should be excluded")
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, "scripts", "gemini-deploy.sh")),
                "gemini-deploy.sh should be excluded from prod",
            )
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, "tests", "test_gemini_deploy.sh")),
                "test_gemini_deploy.sh should be excluded from prod",
            )

    def test_deploy_excludes_sdlc_runs(self):
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            os.makedirs(os.path.join(repo_root, ".sdlc"), exist_ok=True)
            os.makedirs(os.path.join(repo_root, ".sdlc_runs"), exist_ok=True)

            deploy_script = os.path.join(repo_root, "deploy.sh")
            install_fake_python_toolchain(repo_root, env)
            res = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Deploy failed: {res.stderr}\n{res.stdout}")

            prod_dir = os.path.join(mock_home, ".openclaw", "skills", "leio-sdlc")
            self.assertTrue(os.path.exists(prod_dir), "Prod dir not created")
            self.assertFalse(os.path.exists(os.path.join(prod_dir, ".sdlc")), ".sdlc/ directory should be excluded")
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, ".sdlc_runs")),
                ".sdlc_runs/ directory should be excluded",
            )
