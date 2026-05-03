import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

class TestOrchestratorResume(unittest.TestCase):
    @patch("orchestrator.drun")
    @patch("structured_state_parser.update_status")
    @patch("structured_state_parser.get_status")
    @patch("glob.glob")
    @patch("orchestrator.os.open", return_value=999)
    @patch("fcntl.flock")
    @patch("os.path.exists")
    @patch("orchestrator.validate_prd_is_committed")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    @patch("git_utils.check_git_boundary")
    def test_resume_resets_in_progress_pr(self, mock_check_git, mock_parse, mock_validate, mock_exists, mock_flock, mock_os_open, mock_glob, mock_get_status, mock_update_status, mock_drun):
        import orchestrator
        import tempfile
        
        def mock_exists_side_effect(path):
            if "PR_001.md" in str(path) or "job" in str(path) or ".sdlc_runs" in str(path) or ".git" in str(path):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect
        mock_glob.return_value = ["/dummy/job/PR_001.md"]
        mock_get_status.return_value = "in_progress"
        
        def mock_drun_side_effect(*args, **kwargs):
            class Ret:
                stdout = ""
                returncode = 0
            return Ret()
        mock_drun.side_effect = mock_drun_side_effect
        
        td = tempfile.mkdtemp()
        with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--resume", "--test-sleep", "--global-dir", td]):
            with self.assertRaises(SystemExit) as cm:
                orchestrator.main()
            self.assertEqual(cm.exception.code, 0)
            mock_update_status.assert_called_once_with("/dummy/job/PR_001.md", "open")

    @patch("orchestrator.drun")
    @patch("orchestrator.os.open", return_value=999)
    @patch("fcntl.flock")
    @patch("os.path.exists")
    @patch("orchestrator.validate_prd_is_committed")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    @patch("git_utils.check_git_boundary")
    def test_resume_workspace_purification_master(self, mock_check_git, mock_parse, mock_validate, mock_exists, mock_flock, mock_os_open, mock_drun):
        import orchestrator
        import tempfile
        
        def mock_exists_side_effect(path):
            if ".sdlc_runs" in str(path) or ".git" in str(path):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect

        call_count = {"status": 0}

        def mock_drun_side_effect(cmd, *args, **kwargs):
            class Ret:
                stdout = ""
                returncode = 0
            if "status" in cmd:
                if call_count["status"] == 0:
                    Ret.stdout = " M dirty_file.txt"
                call_count["status"] += 1
            elif "branch" in cmd:
                Ret.stdout = "master"
            return Ret()
        mock_drun.side_effect = mock_drun_side_effect
        
        td = tempfile.mkdtemp()
        with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--resume", "--test-sleep", "--global-dir", td]):
            with self.assertRaises(SystemExit):
                orchestrator.main()
            
            # Check that git stash push was called
            calls = mock_drun.call_args_list
            stash_called = any(
                "stash" in call.args[0] and "push" in call.args[0]
                for call in calls
            )
            self.assertTrue(stash_called, "git stash push should be called on master branch")
            
            # Verify branch rename wasn't called
            rename_called = any(
                "branch" in call.args[0] and "-m" in call.args[0]
                for call in calls
            )
            self.assertFalse(rename_called, "git branch -m should NOT be called on master")

    @patch("orchestrator.run_runtime_git")
    @patch("orchestrator.drun")
    @patch("orchestrator.os.open", return_value=999)
    @patch("fcntl.flock")
    @patch("os.path.exists")
    @patch("orchestrator.validate_prd_is_committed")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    @patch("git_utils.check_git_boundary")
    def test_resume_workspace_purification_feature(self, mock_check_git, mock_parse, mock_validate, mock_exists, mock_flock, mock_os_open, mock_drun, mock_run_runtime_git):
        import orchestrator
        import tempfile
        
        def mock_exists_side_effect(path):
            if ".sdlc_runs" in str(path) or ".git" in str(path):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect

        call_count = {"status": 0}

        def mock_drun_side_effect(cmd, *args, **kwargs):
            class Ret:
                stdout = ""
                returncode = 0
            if "status" in cmd:
                if call_count["status"] == 0:
                    Ret.stdout = " M dirty_file.txt"
                call_count["status"] += 1
            elif "branch" in cmd and "--show-current" in cmd:
                Ret.stdout = "feature-branch"
            return Ret()
        mock_drun.side_effect = mock_drun_side_effect
        
        td = tempfile.mkdtemp()
        with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--resume", "--test-sleep", "--global-dir", td]):
            with self.assertRaises(SystemExit):
                orchestrator.main()
            
            calls = mock_drun.call_args_list
            add_called = any("add" in call.args[0] and "-A" in call.args[0] for call in calls)
            rename_called = any("branch" in call.args[0] and "-m" in call.args[0] for call in calls)
            checkout_called = any("checkout" in call.args[0] and "master" in call.args[0] for call in calls)
            
            self.assertTrue(add_called)
            mock_run_runtime_git.assert_called_once_with(
                "orchestrator",
                ["commit", "--allow-empty", "-m", "WIP: 🚨 FORENSIC CRASH STATE"],
                check=False,
            )
            self.assertTrue(rename_called)
            self.assertTrue(checkout_called)

    @patch("orchestrator.drun")
    @patch("orchestrator.os.open", return_value=999)
    @patch("fcntl.flock")
    @patch("os.path.exists")
    @patch("orchestrator.validate_prd_is_committed")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    @patch("git_utils.check_git_boundary")
    def test_resume_clean_workspace(self, mock_check_git, mock_parse, mock_validate, mock_exists, mock_flock, mock_os_open, mock_drun):
        import orchestrator
        import tempfile
        
        def mock_exists_side_effect(path):
            if ".sdlc_runs" in str(path) or ".git" in str(path):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect

        def mock_drun_side_effect(cmd, *args, **kwargs):
            class Ret:
                stdout = ""
                returncode = 0
            # Clean workspace
            return Ret()
        mock_drun.side_effect = mock_drun_side_effect
        
        td = tempfile.mkdtemp()
        with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--resume", "--test-sleep", "--global-dir", td]):
            with self.assertRaises(SystemExit):
                orchestrator.main()
            
            # Check that no purification commands were called
            calls = mock_drun.call_args_list
            purification_called = any(
                "stash" in call.args[0] or 
                ("branch" in call.args[0] and "-m" in call.args[0]) or
                ("add" in call.args[0] and "-A" in call.args[0])
                for call in calls
            )
            self.assertFalse(purification_called)

if __name__ == "__main__":
    unittest.main()
