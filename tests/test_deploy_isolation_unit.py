import os
import subprocess
import unittest
from pathlib import Path
from deploy_test_support import isolated_repo_env, install_fake_python_toolchain


class TestDeployIsolationUnit(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_deploy_hermetic_isolation(self):
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            self.assertNotEqual(os.path.basename(repo_root), "leio-sdlc")
            self.assertEqual(env["HOME_MOCK"], mock_home)
            self.assertEqual(env["HOME"], mock_home)  # Verifying the double-lock fix in support

            deploy_script = os.path.join(repo_root, "deploy.sh")

            # Install fake python toolchain which also sets up env["PATH"] and env["LEIO_DEPLOY_TEST_LOG"]
            log_path = install_fake_python_toolchain(repo_root, env)

            # Now install fake gemini in the same fake-bin
            fake_bin = Path(repo_root) / "fake-bin"
            fake_gemini = fake_bin / "gemini"
            fake_gemini.write_text(
                f"""#!/bin/sh
echo "gemini:HOME=$HOME" >> "{log_path}"
echo "gemini:args=$*" >> "{log_path}"
""",
                encoding="utf-8",
            )
            fake_gemini.chmod(0o755)

            # Run deployment
            res = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Deploy failed: {res.stderr}\n{res.stdout}")

            # Read the log to verify gemini was called with correct HOME
            self.assertTrue(os.path.exists(log_path), "Deploy log not found")
            log_content = Path(log_path).read_text(encoding="utf-8")

            # We expect to see gemini calls in the log
            self.assertIn("gemini:HOME=", log_content, "Gemini was not called or did not log")

            # Verify that every gemini call saw HOME == mock_home
            lines = log_content.splitlines()
            gemini_calls = [line for line in lines if line.startswith("gemini:")]

            self.assertTrue(len(gemini_calls) >= 2, f"Expected at least 2 log lines from gemini, got: {gemini_calls}")

            # Find the HOME line
            home_line = [line for line in gemini_calls if line.startswith("gemini:HOME=")]
            self.assertEqual(len(home_line), 1, f"Expected 1 HOME log, got: {home_line}")
            self.assertEqual(home_line[0], f"gemini:HOME={mock_home}")

            # Find the args line
            args_line = [line for line in gemini_calls if line.startswith("gemini:args=")]
            self.assertEqual(len(args_line), 1, f"Expected 1 args log, got: {args_line}")
            self.assertIn("skills link", args_line[0])
            self.assertIn("--consent", args_line[0])

    def test_pm_skill_deploy_hermetic_isolation(self):
        # We should also test pm-skill deploy.sh
        with isolated_repo_env(self.project_root) as isolated:
            repo_root = isolated["repo_root"]
            mock_home = isolated["mock_home"]
            env = isolated["env"]

            deploy_script = os.path.join(repo_root, "skills", "pm-skill", "deploy.sh")

            # Install fake python toolchain
            log_path = install_fake_python_toolchain(repo_root, env)

            # Install fake gemini
            fake_bin = Path(repo_root) / "fake-bin"
            fake_gemini = fake_bin / "gemini"
            fake_gemini.write_text(
                f"""#!/bin/sh
echo "gemini:HOME=$HOME" >> "{log_path}"
echo "gemini:args=$*" >> "{log_path}"
""",
                encoding="utf-8",
            )
            fake_gemini.chmod(0o755)

            # Run pm-skill deployment
            res = subprocess.run(
                ["bash", deploy_script, "--no-restart"],
                env=env,
                cwd=mock_home,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"PM Skill Deploy failed: {res.stderr}\n{res.stdout}")

            # Verify log
            self.assertTrue(os.path.exists(log_path), "Deploy log not found")
            log_content = Path(log_path).read_text(encoding="utf-8")

            self.assertIn("gemini:HOME=", log_content, "Gemini was not called in pm-skill deploy")

            lines = log_content.splitlines()
            gemini_calls = [line for line in lines if line.startswith("gemini:")]

            home_line = [line for line in gemini_calls if line.startswith("gemini:HOME=")]
            self.assertEqual(len(home_line), 1)
            self.assertEqual(home_line[0], f"gemini:HOME={mock_home}")

            args_line = [line for line in gemini_calls if line.startswith("gemini:args=")]
            self.assertEqual(len(args_line), 1)
            self.assertIn("skills link", args_line[0])
            self.assertIn("--consent", args_line[0])
