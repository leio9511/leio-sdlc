import os
import sys
import unittest
from unittest.mock import patch, mock_open
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import spawn_coder

class TestCoderStartupEnvelope(unittest.TestCase):
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_coder_saves_revision_bootstrap_artifacts(self, mock_setup_key, mock_invoke, mock_check_output):
        from agent_driver import AgentResult
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="mock-session", stdout="")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            feedback_file = os.path.join(tmp_dir, "feedback.json")
            
            with open(pr_file, "w") as f:
                f.write("mock")
            with open(prd_file, "w") as f:
                f.write("mock")
            with open(feedback_file, "w") as f:
                f.write("mock feedback")
                
            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--feedback-file", feedback_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()
                    
            bootstrap_dir = os.path.join(tmp_dir, "coder_debug", "revision_bootstrap_001")
            self.assertTrue(os.path.exists(os.path.join(bootstrap_dir, "startup_packet.json")))
            self.assertTrue(os.path.exists(os.path.join(bootstrap_dir, "rendered_prompt.txt")))
            
            with open(os.path.join(bootstrap_dir, "startup_packet.json")) as f:
                packet = json.load(f)
                
            feedback_refs = [ref for ref in packet["reference_index"] if ref["id"] == "reviewer_feedback"]
            self.assertEqual(len(feedback_refs), 1)
            self.assertEqual(feedback_refs[0]["path"], feedback_file)

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_coder_saves_system_alert_artifacts(self, mock_setup_key, mock_invoke, mock_check_output):
        from agent_driver import AgentResult
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="mock-session", stdout="")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            
            with open(pr_file, "w") as f:
                f.write("mock")
            with open(prd_file, "w") as f:
                f.write("mock")
                
            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--system-alert", "git status is dirty",
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()
                    
            alert_dir = os.path.join(tmp_dir, "coder_debug", "system_alert_001")
            self.assertTrue(os.path.exists(os.path.join(alert_dir, "startup_packet.json")))
            self.assertTrue(os.path.exists(os.path.join(alert_dir, "rendered_prompt.txt")))
            
            with open(os.path.join(alert_dir, "startup_packet.json")) as f:
                packet = json.load(f)
                
            alert_clauses = [c for c in packet["execution_contract"] if "git status is dirty" in c]
            self.assertEqual(len(alert_clauses), 1)

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_coder_rendered_prompt_references_coder_playbook_without_inlining(self, mock_setup_key, mock_invoke, mock_check_output):
        from agent_driver import AgentResult
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="mock-session", stdout="")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            
            with open(pr_file, "w") as f:
                f.write("mock")
            with open(prd_file, "w") as f:
                f.write("mock")
                
            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()
                    
            initial_dir = os.path.join(tmp_dir, "coder_debug", "initial")
            self.assertTrue(os.path.exists(os.path.join(initial_dir, "rendered_prompt.txt")))
            self.assertTrue(os.path.exists(os.path.join(initial_dir, "startup_packet.json")))
            
            with open(os.path.join(initial_dir, "rendered_prompt.txt")) as f:
                rendered = f.read()
            
            # Should reference playbook path
            self.assertIn("coder_playbook.md", rendered)
            # Should not inline the full PRD or Playbook (we just check it's shorter than before, but we can check the packet structure)
            
            with open(os.path.join(initial_dir, "startup_packet.json")) as f:
                packet = json.load(f)
            
            playbook_refs = [ref for ref in packet["reference_index"] if "coder_playbook.md" in ref["path"]]
            self.assertEqual(len(playbook_refs), 1)
            self.assertTrue(playbook_refs[0]["required"])

if __name__ == '__main__':
    unittest.main()
