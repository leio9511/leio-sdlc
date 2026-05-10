import os
import subprocess
import tempfile
import unittest


class TestDeployExcludes(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.deploy_script = os.path.join(self.project_root, "deploy.sh")

    def _deploy_to_mock_home(self, mock_home):
        env = os.environ.copy()
        env["HOME_MOCK"] = mock_home
        result = subprocess.run(
            ["bash", self.deploy_script, "--no-restart"],
            env=env,
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Deploy failed: {result.stderr}\n{result.stdout}")
        return os.path.join(mock_home, ".openclaw", "skills", "leio-sdlc")

    def test_deploy_excludes_tests(self):
        with tempfile.TemporaryDirectory() as tempdir:
            mock_home = os.path.join(tempdir, "home")
            os.makedirs(mock_home, exist_ok=True)

            prod_dir = self._deploy_to_mock_home(mock_home)

            self.assertTrue(os.path.isdir(prod_dir), "Prod dir not created")
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, "tests")),
                "tests/ directory should be excluded from deployed artifacts",
            )

    def test_deploy_excludes_sdlc_runs(self):
        source_sdlc_dir = os.path.join(self.project_root, ".sdlc")
        source_sdlc_runs_dir = os.path.join(self.project_root, ".sdlc_runs")

        with tempfile.TemporaryDirectory() as tempdir:
            mock_home = os.path.join(tempdir, "home")
            os.makedirs(mock_home, exist_ok=True)
            os.makedirs(source_sdlc_dir, exist_ok=True)
            os.makedirs(source_sdlc_runs_dir, exist_ok=True)

            prod_dir = self._deploy_to_mock_home(mock_home)

            self.assertTrue(os.path.isdir(prod_dir), "Prod dir not created")
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, ".sdlc")),
                ".sdlc/ directory should be excluded from deployed artifacts",
            )
            self.assertFalse(
                os.path.exists(os.path.join(prod_dir, ".sdlc_runs")),
                ".sdlc_runs/ directory should be excluded from deployed artifacts",
            )


if __name__ == "__main__":
    unittest.main()
