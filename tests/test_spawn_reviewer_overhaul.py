import os
import subprocess
import tempfile
import json
import unittest

class TestSpawnReviewerOverhaul(unittest.TestCase):
    def setUp(self):
        self.workdir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        self.run_dir = tempfile.mkdtemp()
        self.pr_file = os.path.join(self.run_dir, "PR_002_dummy.md")
        with open(self.pr_file, "w") as f:
            f.write("Dummy PR Content")
        self.diff_file = os.path.join(self.run_dir, "dummy.diff")
        with open(self.diff_file, "w") as f:
            f.write("+++ b/dummy.py")
        self.out_file = "review_report.json"
        
        self.env = os.environ.copy()
        self.env["SDLC_TEST_MODE"] = "true"

    def test_spawn_reviewer_scaffolds_file(self):
        # We want to test that it writes NOT_STARTED before execution.
        # If we mock the failure, it will leave the file as NOT_STARTED,
        # but the script will exit with 1 because verification fails.
        self.env["SDLC_MOCK_REVIEWER_FAILURE"] = "true"
        
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", self.workdir,
            "--pr-file", self.pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", self.diff_file,
            "--run-dir", self.run_dir,
            "--out-file", self.out_file
        ]
        
        result = subprocess.run(cmd, env=self.env, cwd=self.workdir, capture_output=True, text=True)
        
        # Expect fatal error from rigid verification
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FATAL]", result.stderr)
        
        # The file should contain the NOT_STARTED assessment
        report_path = os.path.join(self.run_dir, self.out_file)
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("overall_assessment"), "NOT_STARTED")

    def test_spawn_reviewer_rigid_verification(self):
        # Testing rigid verification where the file remains NOT_STARTED
        self.env["SDLC_MOCK_REVIEWER_FAILURE"] = "true"
        
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", self.workdir,
            "--pr-file", self.pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", self.diff_file,
            "--run-dir", self.run_dir,
            "--out-file", self.out_file
        ]
        
        result = subprocess.run(cmd, env=self.env, cwd=self.workdir, capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FATAL] The Reviewer agent failed to change overall_assessment from NOT_STARTED. Audit failed.", result.stderr)

    def test_spawn_reviewer_success(self):
        # Testing success scenario where file contains valid JSON and is not NOT_STARTED
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", self.workdir,
            "--pr-file", self.pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", self.diff_file,
            "--run-dir", self.run_dir,
            "--out-file", self.out_file
        ]
        
        result = subprocess.run(cmd, env=self.env, cwd=self.workdir, capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 0)
        
        report_path = os.path.join(self.run_dir, self.out_file)
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("overall_assessment"), "APPROVED")
        
    def test_spawn_reviewer_invalid_json(self):
        self.env["SDLC_MOCK_REVIEWER_INVALID_JSON"] = "true"
        
        cmd = [
            "python3", "scripts/spawn_reviewer.py",
            "--workdir", self.workdir,
            "--pr-file", self.pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", self.diff_file,
            "--run-dir", self.run_dir,
            "--out-file", self.out_file
        ]
        
        result = subprocess.run(cmd, env=self.env, cwd=self.workdir, capture_output=True, text=True)
        
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FATAL] Invalid JSON in review report", result.stderr)

if __name__ == "__main__":
    unittest.main()
