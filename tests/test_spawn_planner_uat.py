import unittest
import os
import sys
import subprocess
import json
import tempfile
import shutil

class TestSpawnPlannerUAT(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workdir = os.path.join(self.temp_dir, "workdir")
        os.makedirs(self.workdir)
        self.run_dir = os.path.join(self.temp_dir, "run_dir")
        os.makedirs(self.run_dir)
        
        self.prd_file = os.path.join(self.temp_dir, "PRD.md")
        with open(self.prd_file, "w") as f:
            f.write("# Dummy PRD\n")
            
        self.uat_report_file = os.path.join(self.temp_dir, "uat_report.json")
        with open(self.uat_report_file, "w") as f:
            json.dump({"status": "NEEDS_FIX", "missing": ["Log output missing"]}, f)
            
        self.script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts', 'spawn_planner.py'))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_planner_replan_uat_failures_argument(self):
        # Expected: Verifies that spawn_planner.py successfully parses the --replan-uat-failures CLI argument and loads the JSON report
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        cmd = [
            sys.executable, self.script_path,
            "--prd-file", self.prd_file,
            "--workdir", self.workdir,
            "--run-dir", self.run_dir,
            "--replan-uat-failures", self.uat_report_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, f"Script failed: {result.stderr}")
        
        # Check tool_calls.log to see if replan_uat_failures was parsed
        log_file = os.path.join(self.run_dir, "tests", "tool_calls.log")
        self.assertTrue(os.path.exists(log_file), "tool_calls.log not found")
        with open(log_file, "r") as f:
            log_content = f.read()
            
        self.assertIn("replan_uat_failures", log_content)
        self.assertIn(self.uat_report_file, log_content)

    def test_planner_uses_recovery_prompt(self):
        # Expected: Verifies that the specialized recovery prompt is injected precisely when the flag is present
        env = os.environ.copy()
        env["SDLC_TEST_MODE"] = "true"
        cmd = [
            sys.executable, self.script_path,
            "--prd-file", self.prd_file,
            "--workdir", self.workdir,
            "--run-dir", self.run_dir,
            "--replan-uat-failures", self.uat_report_file
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0)
        
        # Check task_string.log
        task_log = os.path.join(self.run_dir, "tests", "task_string.log")
        self.assertTrue(os.path.exists(task_log), "task_string.log not found")
        with open(task_log, "r") as f:
            task_content = f.read()
            
        expected_prompt = "作为一个架构师，不要重新规划已有的功能。请仔细阅读 UAT 报告中标记为 MISSING 的需求，生成专门针对这些遗漏点的新 Micro-PRs（例如 PR_UAT_Fix_1.md），确保不破坏现有代码。"
        self.assertIn(expected_prompt, task_content)
        self.assertIn("Log output missing", task_content) # from UAT report

if __name__ == '__main__':
    unittest.main()
