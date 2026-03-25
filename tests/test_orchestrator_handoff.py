import sys
import os
import unittest
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import orchestrator
from handoff_prompter import HandoffPrompter

class TestOrchestratorHandoffIntegration(unittest.TestCase):
    @patch('subprocess.run')
    @patch('sys.exit')
    @patch('builtins.print')
    def test_dirty_workspace(self, mock_print, mock_exit, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = " M file.txt\n"
        mock_run.return_value = mock_result
        mock_exit.side_effect = SystemExit(1)
        
        with self.assertRaises(SystemExit):
            orchestrator.main()
            
        mock_print.assert_any_call(HandoffPrompter.get_prompt("dirty_workspace"))

    @patch('sys.exit')
    @patch('builtins.print')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('subprocess.run')
    def test_planner_failure(self, mock_run, mock_args, mock_glob, mock_exists, mock_print, mock_exit):
        args = MagicMock()
        args.workdir = "/dummy"
        args.prd_file = "dummy.md"
        args.job_dir = "docs/PRs/dummy"
        args.force_replan = False
        args.notify_channel = None
        args.notify_target = None
        mock_args.return_value = args
        
        def mock_run_side_effect(cmd, *a, **kw):
            res = MagicMock()
            res.stdout = ""
            res.returncode = 0
            return res
        mock_run.side_effect = mock_run_side_effect
        
        def mock_exists_side_effect(path):
            if path == "/dummy": return True
            if "job_dir" in path or "docs/PRs/dummy" in path: return False
            return False
        mock_exists.side_effect = mock_exists_side_effect
        
        mock_exit.side_effect = SystemExit(1)
        
        with patch('os.chdir'):
            with self.assertRaises(SystemExit):
                orchestrator.main()
                
        mock_print.assert_any_call(HandoffPrompter.get_prompt("planner_failure"))

    @patch('sys.exit')
    @patch('builtins.print')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('subprocess.run')
    def test_queue_empty(self, mock_run, mock_args, mock_glob, mock_exists, mock_print, mock_exit):
        args = MagicMock()
        args.workdir = "/dummy"
        args.prd_file = "dummy.md"
        args.job_dir = "docs/PRs/dummy"
        args.force_replan = False
        args.notify_channel = None
        args.notify_target = None
        args.max_runs = 0
        args.coder_session_strategy = "on-escalation"
        mock_args.return_value = args
        
        def mock_run_side_effect(cmd, *a, **kw):
            res = MagicMock()
            if cmd == ["git", "status", "--porcelain"]:
                res.stdout = ""
            elif len(cmd) > 1 and "get_next_pr.py" in cmd[1]:
                res.stdout = "[QUEUE_EMPTY]"
            else:
                res.stdout = ""
            res.returncode = 0
            return res
        mock_run.side_effect = mock_run_side_effect
        
        def mock_exists_side_effect(path):
            if path == "/dummy": return True
            if "docs/PRs/dummy" in path: return True
            return False
        mock_exists.side_effect = mock_exists_side_effect
        
        mock_glob.return_value = ["/dummy/docs/PRs/dummy/PR_001.md"]
        
        with patch('builtins.open', unittest.mock.mock_open(read_data="status: closed\n")):
            mock_exit.side_effect = SystemExit(0)
            with patch('os.chdir'):
                with self.assertRaises(SystemExit):
                    orchestrator.main()
                    
            mock_print.assert_any_call(HandoffPrompter.get_prompt("happy_path"))

    @patch('sys.exit')
    @patch('builtins.print')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('subprocess.run')
    def test_git_checkout_error(self, mock_run, mock_args, mock_glob, mock_exists, mock_print, mock_exit):
        args = MagicMock()
        args.workdir = "/dummy"
        args.prd_file = "dummy.md"
        args.job_dir = "docs/PRs/dummy"
        args.force_replan = False
        args.notify_channel = None
        args.notify_target = None
        args.max_runs = 1
        args.coder_session_strategy = "on-escalation"
        mock_args.return_value = args
        
        def mock_run_side_effect(cmd, *a, **kw):
            res = MagicMock()
            if cmd == ["git", "status", "--porcelain"]:
                res.stdout = ""
                res.returncode = 0
            elif len(cmd) > 1 and "get_next_pr.py" in cmd[1]:
                res.stdout = "PR_001.md"
                res.returncode = 0
            elif cmd == ["git", "diff", "--cached", "--quiet"]:
                res.returncode = 0
            elif len(cmd) > 1 and "git" == cmd[0] and "show-ref" == cmd[1]:
                res.returncode = 0
            else:
                res.stdout = ""
                res.returncode = 0
            return res
        mock_run.side_effect = mock_run_side_effect
        
        def mock_exists_side_effect(path):
            if path == "/dummy": return True
            if "docs/PRs/dummy" in path: return True
            if path == "PR_001.md": return True
            return False
        mock_exists.side_effect = mock_exists_side_effect
        
        mock_glob.return_value = ["/dummy/docs/PRs/dummy/PR_001.md"]
        
        with patch('builtins.open', unittest.mock.mock_open(read_data="status: in_progress\n")):
            mock_exit.side_effect = SystemExit(1)
            with patch('os.chdir'):
                with patch('orchestrator.safe_git_checkout', side_effect=orchestrator.GitCheckoutError("Mock Git Error")):
                    with self.assertRaises(SystemExit):
                        orchestrator.main()
                    
            mock_print.assert_any_call(HandoffPrompter.get_prompt("git_checkout_error"))
            
    @patch('sys.exit')
    @patch('builtins.print')
    @patch('os.path.exists')
    @patch('glob.glob')
    @patch('argparse.ArgumentParser.parse_args')
    @patch('subprocess.run')
    def test_dead_end(self, mock_run, mock_args, mock_glob, mock_exists, mock_print, mock_exit):
        args = MagicMock()
        args.workdir = "/dummy"
        args.prd_file = "dummy.md"
        args.job_dir = "docs/PRs/dummy"
        args.force_replan = False
        args.notify_channel = None
        args.notify_target = None
        args.max_runs = 1
        args.coder_session_strategy = "on-escalation"
        mock_args.return_value = args
        
        def mock_run_side_effect(cmd, *a, **kw):
            res = MagicMock()
            if cmd == ["git", "status", "--porcelain"]:
                res.stdout = ""
                res.returncode = 0
            elif len(cmd) > 1 and "get_next_pr.py" in cmd[1]:
                res.stdout = "PR_001.md"
                res.returncode = 0
            elif cmd == ["git", "diff", "--cached", "--quiet"]:
                res.returncode = 0
            elif len(cmd) > 1 and "git" == cmd[0] and "show-ref" == cmd[1]:
                res.returncode = 0
            elif len(cmd) > 1 and "spawn_reviewer.py" in cmd[1]:
                res.returncode = 0
            elif len(cmd) > 1 and "spawn_coder.py" in cmd[1]:
                res.returncode = 1
            else:
                res.stdout = ""
                res.returncode = 0
            return res
        mock_run.side_effect = mock_run_side_effect
        
        def mock_exists_side_effect(path):
            if path == "/dummy": return True
            if "docs/PRs/dummy" in path: return True
            if path == "PR_001.md": return True
            return False
        mock_exists.side_effect = mock_exists_side_effect
        
        mock_glob.return_value = ["/dummy/docs/PRs/dummy/PR_001.md"]
        
        with patch('builtins.open', unittest.mock.mock_open(read_data="status: in_progress\nslice_depth: 2\n")):
            mock_exit.side_effect = SystemExit(1)
            with patch('os.chdir'):
                with patch('orchestrator.safe_git_checkout', return_value=None):
                    with self.assertRaises(SystemExit):
                        orchestrator.main()
                    
            mock_print.assert_any_call(HandoffPrompter.get_prompt("dead_end"))

if __name__ == '__main__':
    unittest.main()
