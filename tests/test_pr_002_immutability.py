import unittest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import orchestrator
import create_pr_contract

class TestPR002Immutability(unittest.TestCase):
    @patch('orchestrator.subprocess.run')
    def test_set_pr_status_stages_only_modified_file(self, mock_run):
        # Create a dummy PR file
        pr_file = "dummy_pr.md"
        with open(pr_file, 'w') as f:
            f.write("status: open\n")
            
        orchestrator.set_pr_status(pr_file, "in_progress")
        
        # Verify subprocess.run calls
        mock_run.assert_any_call(["git", "add", pr_file], check=False)
        mock_run.assert_any_call(["git", "commit", "-m", "chore(state): update PR state to in_progress"], check=False)
        
        # Verify no git add .
        for call in mock_run.call_args_list:
            self.assertNotEqual(call[0][0], ["git", "add", "."])
            
        os.remove(pr_file)

    def test_append_to_pr_removed(self):
        # Verify append_to_pr does not exist in orchestrator
        self.assertFalse(hasattr(orchestrator, 'append_to_pr'))

    @patch('subprocess.run')
    def test_create_pr_contract_git_add(self, mock_run):
        test_workdir = os.path.abspath(".")
        job_dir = os.path.join(test_workdir, "dummy_job_dir")
        os.makedirs(job_dir, exist_ok=True)
        
        content_file = "dummy_content.md"
        with open(content_file, "w") as f:
            f.write("content")
            
        sys.argv = ["create_pr_contract.py", "--workdir", test_workdir, "--job-dir", job_dir, "--title", "Test PR", "--content-file", content_file]
        
        try:
            create_pr_contract.main()
        except SystemExit:
            pass
            
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0:2], ["git", "add"])
        
        # Cleanup
        import shutil
        shutil.rmtree(job_dir)
        os.remove(content_file)

if __name__ == '__main__':
    unittest.main()
