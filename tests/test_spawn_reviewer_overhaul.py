import os
import sys
import subprocess
import tempfile
import json
import unittest
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

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
        self.env["SDLC_MOCK_REVIEWER_FAILURE"] = "true"
        cmd = [
            "python3", "scripts/spawn_reviewer.py", "--enable-exec-from-workspace",
            "--workdir", self.workdir,
            "--pr-file", self.pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", self.diff_file,
            "--run-dir", self.run_dir,
            "--out-file", self.out_file
        ]
        result = subprocess.run(cmd, env=self.env, cwd=self.workdir, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[FATAL]", result.stderr)
        report_path = os.path.join(self.run_dir, self.out_file)
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("overall_assessment"), "NOT_STARTED")

    def test_spawn_reviewer_rigid_verification(self):
        self.env["SDLC_MOCK_REVIEWER_FAILURE"] = "true"
        cmd = [
            "python3", "scripts/spawn_reviewer.py", "--enable-exec-from-workspace",
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
        cmd = [
            "python3", "scripts/spawn_reviewer.py", "--enable-exec-from-workspace",
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
            "python3", "scripts/spawn_reviewer.py", "--enable-exec-from-workspace",
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

    def test_reviewer_aligned_to_file_based_result_subprocess(self):
        cmd = [
            "python3", "scripts/spawn_reviewer.py", "--enable-exec-from-workspace",
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
        with open(report_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data.get("overall_assessment"), "APPROVED")


class TestSpawnReviewerAligned(unittest.TestCase):
    @patch('spawn_reviewer.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_reviewer_aligned_to_file_based_result(self, mock_setup_key, mock_invoke_agent):
        import spawn_reviewer
        from agent_driver import AgentResult
        
        # We need a setup
        workdir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        run_dir = tempfile.mkdtemp()
        pr_file = os.path.join(run_dir, "PR_002_dummy.md")
        with open(pr_file, "w") as f:
            f.write("Dummy PR Content")
        diff_file = os.path.join(run_dir, "dummy.diff")
        with open(diff_file, "w") as f:
            f.write("+++ b/dummy.py")
            
        out_file = "review_report.json"
        report_path = os.path.join(run_dir, out_file)

        # Before invoke_agent finishes, we must simulate that the agent created the file properly
        def side_effect(*args, **kwargs):
            with open(report_path, "w") as f:
                f.write('{"overall_assessment": "APPROVED", "executive_summary": "Mock", "findings": []}')
            return AgentResult(session_key='subtask-reviewer', stdout='Some unrelated conversational text')
            
        mock_invoke_agent.side_effect = side_effect

        test_args = [
            "spawn_reviewer.py", "--enable-exec-from-workspace",
            "--workdir", workdir,
            "--pr-file", pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", diff_file,
            "--run-dir", run_dir,
            "--out-file", out_file
        ]
        
        with patch.object(sys, 'argv', test_args):
            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
                try:
                    spawn_reviewer.main()
                except SystemExit as e:
                    self.assertEqual(e.code, 0, "spawn_reviewer should exit 0 when file is valid, despite non-JSON stdout")
                    
        self.assertTrue(mock_invoke_agent.called)

if __name__ == "__main__":
    unittest.main()
