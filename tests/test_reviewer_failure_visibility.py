import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import orchestrator

class TestReviewerFailureVisibility(unittest.TestCase):
    
    def _run_orchestrator(self, workdir, global_dir, review_report_content, missing_artifact=False):
        import shutil
        job_dir = os.path.join(global_dir, ".sdlc_runs", os.path.basename(workdir), "dummy_prd")
        os.makedirs(job_dir, exist_ok=True)
        pr_file = os.path.join(job_dir, "PR_001.md")
        with open(pr_file, "w") as f:
            f.write("---\nstatus: in_progress\n---\n")
            
        def mock_dpopen(cmd, *args, **kwargs):
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "spawn_planner.py" in cmd_str:
                    proc = MagicMock()
                    proc.returncode = 0
                    return proc
                if "spawn_coder.py" in cmd_str:
                    proc = MagicMock()
                    proc.returncode = 0
                    return proc
                if "spawn_reviewer.py" in cmd_str:
                    # simulate reviewer creating the artifact
                    if not missing_artifact:
                        review_artifact = os.path.join(global_dir, ".sdlc_runs", os.path.basename(workdir), "dummy_prd", "review_report.json")
                        with open(review_artifact, "w") as f:
                            f.write(review_report_content)
                    proc = MagicMock()
                    proc.returncode = 0
                    return proc
            proc = MagicMock()
            proc.returncode = 0
            return proc

        def dummy_drun(cmd, *args, **kwargs):
            res = MagicMock()
            res.returncode = 0
            res.stdout = ""
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
                if "branch" in cmd_str:
                    res.stdout = "master\n"
                if "git" in cmd_str and "rev-parse" in cmd_str:
                    res.stdout = "deadbeef\n"
                if "preflight.sh" in cmd_str:
                    res.stdout = "ok"
            return res

        mock_notify = MagicMock()
        
        test_args = [
            "orchestrator.py",
            "--workdir", workdir,
            "--global-dir", global_dir,
            "--prd-file", "dummy_prd.md",
            "--force-replan", "false",
            "--enable-exec-from-workspace",
            "--channel", "test-channel",
            "--max-prs-to-process", "1"
        ]

        with patch("sys.argv", test_args), \
             patch("orchestrator.SanityContext.perform_healthy_check"), \
             patch("orchestrator.validate_prd_is_committed"), \
             patch("git_utils.check_git_boundary"), \
             patch("orchestrator.parse_affected_projects", return_value=[]), \
             patch("orchestrator.safe_git_checkout"), \
             patch("orchestrator.teardown_coder_session"), \
             patch("orchestrator.subprocess.run", side_effect=dummy_drun), \
             patch("orchestrator.dpopen", side_effect=mock_dpopen), \
             patch("orchestrator.drun", side_effect=dummy_drun), \
             patch("orchestrator.notify_channel", mock_notify), \
             patch("orchestrator.get_mainline_branch", return_value="master"), \
             patch("orchestrator.get_head_commit_hash", return_value="deadbeef"), \
             patch("orchestrator.classify_coder_null_output", return_value=(False, "", "deadbeef")), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("orchestrator.get_env_with_gemini_key", return_value=os.environ.copy()), \
             patch("orchestrator.glob.glob", side_effect=lambda pattern, **kwargs: [pr_file] if "PR_*.md" in pattern or "*.md" in pattern else []):
            try:
                orchestrator.main()
            except SystemExit:
                pass
        
        return mock_notify

    def test_reviewer_invalid_json_notification(self):
        with tempfile.TemporaryDirectory() as td:
            workdir = os.path.join(td, "workdir")
            global_dir = os.path.join(td, "global")
            os.makedirs(os.path.join(workdir, ".git"))
            
            mock_notify = self._run_orchestrator(workdir, global_dir, "Invalid JSON content")
            
            calls = mock_notify.call_args_list
            notified_event_types = [call[0][2] for call in calls]
            self.assertIn("reviewer_invalid_json", notified_event_types,
                          f"Expected 'reviewer_invalid_json' to be notified, got {notified_event_types}")

    def test_reviewer_missing_artifact_notification(self):
        with tempfile.TemporaryDirectory() as td:
            workdir = os.path.join(td, "workdir")
            global_dir = os.path.join(td, "global")
            os.makedirs(os.path.join(workdir, ".git"))
            
            mock_notify = self._run_orchestrator(workdir, global_dir, "", missing_artifact=True)
            
            calls = mock_notify.call_args_list
            notified_event_types = [call[0][2] for call in calls]
            self.assertIn("reviewer_no_output", notified_event_types,
                          f"Expected 'reviewer_no_output' to be notified, got {notified_event_types}")

    def test_normal_reviewer_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            workdir = os.path.join(td, "workdir")
            global_dir = os.path.join(td, "global")
            os.makedirs(os.path.join(workdir, ".git"))
            
            valid_rejection_json = '{"overall_assessment": "NEEDS_ATTENTION", "findings": ["bug"]}'
            mock_notify = self._run_orchestrator(workdir, global_dir, valid_rejection_json)
            
            calls = mock_notify.call_args_list
            notified_event_types = [call[0][2] for call in calls]
            self.assertIn("review_rejected", notified_event_types,
                          f"Expected 'review_rejected' to be notified, got {notified_event_types}")

if __name__ == "__main__":
    unittest.main()
