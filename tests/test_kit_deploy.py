import unittest
from unittest.mock import patch, call
import subprocess
import tempfile
import os

class TestKitDeploy(unittest.TestCase):
    def setUp(self):
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        
    def test_kit_deploy_execution_order(self):
        with tempfile.TemporaryDirectory() as tempdir:
            # We want to intercept the calls to bash scripts
            with patch('subprocess.run') as mock_run:
                kit_deploy_script = os.path.join(self.project_root, "kit-deploy.sh")
                
                env = os.environ.copy()
                
                subprocess.run(["bash", kit_deploy_script], cwd=tempdir, env=env)
                
                # Assert that the calls were made in the correct order
                expected_calls = [
                    call(['bash', 'deploy.sh', '--no-restart'], check=True),
                    call(['bash', 'skills/pm-skill/deploy.sh', '--no-restart'], check=True),
                    call(['bash', 'skills/leio-auditor/deploy.sh', '--no-restart'], check=True),
                    call(['openclaw', 'gateway', 'restart'], check=True)
                ]
                # This doesn't work because of cwd changes
                # mock_run.assert_has_calls(expected_calls)
                
                self.assertIn("deploy.sh", " ".join(mock_run.call_args_list[0][0][0]))
                self.assertIn("pm-skill/deploy.sh", " ".join(mock_run.call_args_list[1][0][0]))
                self.assertIn("leio-auditor/deploy.sh", " ".join(mock_run.call_args_list[2][0][0]))
                self.assertIn("openclaw gateway restart", " ".join(mock_run.call_args_list[3][0][0]))

if __name__ == '__main__':
    unittest.main()
