import os
import sys
import unittest
import tempfile
from unittest.mock import patch, MagicMock

# Add scripts dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import spawn_coder
from agent_driver import AgentResult

class TestSpawnCoderRefactor(unittest.TestCase):
    def setUp(self):
        self.original_exists = os.path.exists

    @patch('spawn_coder.invoke_agent')
    @patch('spawn_coder.os.chdir')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.os.path.exists')
    def test_spawn_coder_uses_invoke_agent(self, mock_exists, mock_check_output, mock_chdir, mock_invoke):
        mock_check_output.return_value = "feature-branch\n"
        mock_invoke.return_value = AgentResult(session_key="mocked-session-key", stdout="")
        
        # Create real temp files to avoid patching builtins.open
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, 'PR_001.md')
            prd_file = os.path.join(tmp_dir, 'PRD.md')
            with open(pr_file, 'w') as f: f.write('pr content')
            with open(prd_file, 'w') as f: f.write('prd content')
            
            def fake_exists(path):
                if ".coder_session" in path: return False
                if path in [pr_file, prd_file, tmp_dir]: return True
                return self.original_exists(path)
            mock_exists.side_effect = fake_exists
            
            # Test basic invocation
            test_args = [
                'spawn_coder.py',
                "--enable-exec-from-workspace",
                '--pr-file', pr_file,
                '--prd-file', prd_file,
                '--workdir', tmp_dir,
                '--engine', 'gemini',
                '--model', 'gemini-3.1-pro-preview'
            ]
            
            with patch('sys.argv', test_args):
                # Ensure LLM_DRIVER is not set to gemini already to trigger the update logic
                env = {"SDLC_TEST_MODE": "false", "LLM_DRIVER": "openclaw"}
                with patch.dict(os.environ, env):
                    try:
                        spawn_coder.main()
                    except SystemExit:
                        pass
                    # Verify that the environment was updated within the context
                    self.assertEqual(os.environ.get("LLM_DRIVER"), "gemini")
        self.assertEqual(mock_invoke.call_args[1].get('role'), "coder")
        
    @patch('spawn_coder.invoke_agent')
    @patch('spawn_coder.os.chdir')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.os.path.exists')
    def test_spawn_coder_rejection_feedback_loop(self, mock_exists, mock_check_output, mock_chdir, mock_invoke):
        mock_check_output.return_value = "feature-branch\n"
        mock_invoke.return_value = AgentResult(session_key="session-1234", stdout="")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, 'PR_001.md')
            prd_file = os.path.join(tmp_dir, 'PRD.md')
            feedback_file = os.path.join(tmp_dir, 'feedback.json')
            session_file = os.path.join(tmp_dir, '.coder_session')
            
            with open(pr_file, 'w') as f: f.write('pr content')
            with open(prd_file, 'w') as f: f.write('prd content')
            with open(feedback_file, 'w') as f: f.write('{"status": "NEEDS_IMMEDIATE_REWORK", "comments": "Fix it"}')
            with open(session_file, 'w') as f: f.write('session-1234')
            
            def fake_exists(path):
                if path in [pr_file, prd_file, feedback_file, session_file, tmp_dir]: return True
                return self.original_exists(path)
            mock_exists.side_effect = fake_exists
            
            test_args = [
                'spawn_coder.py',
                "--enable-exec-from-workspace",
                '--pr-file', pr_file,
                '--prd-file', prd_file,
                '--workdir', tmp_dir,
                '--feedback-file', feedback_file,
                '--run-dir', tmp_dir
            ]
            
            with patch('sys.argv', test_args):
                with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
                    try:
                        spawn_coder.main()
                    except SystemExit:
                        pass
                    
        mock_invoke.assert_called()
        # Verify feedback was sent using invoke_agent with the correct session key and run_dir
        call_kwargs = mock_invoke.call_args[1]
        self.assertEqual(call_kwargs.get('session_key'), "session-1234")
        self.assertEqual(call_kwargs.get('run_dir'), tmp_dir)
        self.assertEqual(call_kwargs.get('role'), "coder")

if __name__ == '__main__':
    unittest.main()
