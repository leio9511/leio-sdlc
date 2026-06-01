import unittest
import subprocess
import tempfile
import os


class TestKitDeploy(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    def test_kit_deploy_execution_order(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_file = os.path.join(tempdir, "execution.log")

            with open(os.path.join(tempdir, "deploy.sh"), "w") as f:
                f.write(f"#!/bin/bash\necho 'deploy-sdlc --no-restart' >> {log_file}\n")
            os.chmod(os.path.join(tempdir, "deploy.sh"), 0o755)

            os.makedirs(os.path.join(tempdir, "skills", "pm-skill"), exist_ok=True)
            with open(os.path.join(tempdir, "skills", "pm-skill", "deploy.sh"), "w") as f:
                f.write(f"#!/bin/bash\necho 'deploy-pm --no-restart' >> {log_file}\n")
            os.chmod(os.path.join(tempdir, "skills", "pm-skill", "deploy.sh"), 0o755)

            kit_deploy_src = os.path.join(self.project_root, "kit-deploy.sh")
            kit_deploy_dest = os.path.join(tempdir, "kit-deploy.sh")
            with open(kit_deploy_src, "r") as f_src, open(kit_deploy_dest, "w") as f_dest:
                f_dest.write(f_src.read())
            os.chmod(kit_deploy_dest, 0o755)

            env = os.environ.copy()
            env["PATH"] = f"{tempdir}:{env['PATH']}"
            with open(os.path.join(tempdir, "openclaw"), "w") as f:
                f.write(f"#!/bin/bash\necho \"mock-openclaw $*\" >> {log_file}\n")
            os.chmod(os.path.join(tempdir, "openclaw"), 0o755)

            if "HOME_MOCK" in env:
                del env["HOME_MOCK"]

            subprocess.run(["bash", "kit-deploy.sh"], cwd=tempdir, env=env, capture_output=True, text=True, check=True)

            self.assertTrue(os.path.exists(log_file), "Execution log was not created")
            with open(log_file, "r") as f:
                lines = f.read().strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0], "deploy-sdlc --no-restart")
            self.assertEqual(lines[1], "deploy-pm --no-restart")
            self.assertNotIn("mock-openclaw gateway restart", lines)

    def test_kit_deploy_preflight_does_not_run_child_deploys(self):
        with tempfile.TemporaryDirectory() as tempdir:
            log_file = os.path.join(tempdir, "execution.log")

            with open(os.path.join(tempdir, "deploy.sh"), "w") as f:
                f.write(f"#!/bin/bash\necho 'deploy-sdlc --preflight' >> {log_file}\nexit 0\n")
            os.chmod(os.path.join(tempdir, "deploy.sh"), 0o755)

            os.makedirs(os.path.join(tempdir, "skills", "pm-skill"), exist_ok=True)
            with open(os.path.join(tempdir, "skills", "pm-skill", "deploy.sh"), "w") as f:
                f.write(f"#!/bin/bash\necho 'deploy-pm --unexpected' >> {log_file}\nexit 0\n")
            os.chmod(os.path.join(tempdir, "skills", "pm-skill", "deploy.sh"), 0o755)

            kit_deploy_src = os.path.join(self.project_root, "kit-deploy.sh")
            kit_deploy_dest = os.path.join(tempdir, "kit-deploy.sh")
            with open(kit_deploy_src, "r") as f_src, open(kit_deploy_dest, "w") as f_dest:
                f_dest.write(f_src.read())
            os.chmod(kit_deploy_dest, 0o755)

            result = subprocess.run(
                ["bash", "kit-deploy.sh", "--preflight"],
                cwd=tempdir,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                check=True,
            )

            self.assertIn("Kit deployment preflight complete", result.stdout)
            with open(log_file, "r") as f:
                lines = f.read().strip().split("\n")
            self.assertEqual(lines, ["deploy-sdlc --preflight"])

    def test_pm_skill_deploy_script_content(self):
        # pm-skill/deploy.sh is now a thin wrapper delegating to the generic substrate.
        # Gemini linking logic lives in scripts/skill_deploy_lib.sh.
        deploy_sh_path = os.path.join(self.project_root, "skills", "pm-skill", "deploy.sh")
        with open(deploy_sh_path, "r") as f:
            content = f.read()

        # Thin wrapper must delegate to the generic mechanism
        self.assertIn("bash \"$REPO_ROOT/scripts/skill_deploy.sh\" pm-skill", content)
        self.assertNotIn("openclaw gateway restart", content)

        # Gemini linking lives in the shared library
        lib_path = os.path.join(self.project_root, "scripts", "skill_deploy_lib.sh")
        with open(lib_path, "r") as f:
            lib_content = f.read()
        self.assertIn('gemini skills link "$PROD_DIR" --consent', lib_content)


if __name__ == '__main__':
    unittest.main()
