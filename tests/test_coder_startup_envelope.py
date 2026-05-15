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
            with open(os.path.join(bootstrap_dir, "rendered_prompt.txt")) as f:
                rendered_prompt = f.read()
                
            self.assertEqual(packet["mode"], "revision_bootstrap")
            self.assertEqual(packet["lifecycle"], "recovery_bootstrap_continuation")
            self.assertFalse(packet["continuation_semantics"]["fresh_task"])
            self.assertIn(spawn_coder.RECOVERY_CONTINUATION_WARNING, rendered_prompt)
            self.assertIn("# REVIEW REPORT JSON", rendered_prompt)
            self.assertIn("mock feedback", rendered_prompt)
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
            
            self.assertEqual(packet["mode"], "system_alert_bootstrap")
            self.assertEqual(packet["lifecycle"], "recovery_bootstrap_continuation")
            self.assertFalse(packet["continuation_semantics"]["fresh_task"])
            
            with open(os.path.join(alert_dir, "rendered_prompt.txt")) as f:
                prompt_text = f.read()
            self.assertIn("git status is dirty", prompt_text)
            self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt_text)

    @patch('spawn_coder.config.load_or_merge_config', return_value={"coder_playbook_version": 2})
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_initial_v2_prompt_inlines_coder_playbook_and_keeps_pr_contract_and_prd_as_refs(self, mock_setup_key, mock_invoke, mock_check_output, mock_load_config):
        from agent_driver import AgentResult
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="mock-session", stdout="")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            
            with open(pr_file, "w") as f:
                f.write("UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED")
            with open(prd_file, "w") as f:
                f.write("UNIQUE PRD BODY SHOULD NOT BE INLINED")
                
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
            with open(os.path.join(initial_dir, "startup_packet.json")) as f:
                packet = json.load(f)

            self.assertEqual(packet["startup_version"], "v2")
            self.assertEqual(packet["mode"], "initial")
            self.assertIn("## CODER PLAYBOOK", rendered)
            self.assertIn("# Coder Playbook V2", rendered)
            self.assertIn("Red → Green → Refactor", rendered)
            self.assertIn(pr_file, rendered)
            self.assertIn(prd_file, rendered)
            self.assertNotIn("UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED", rendered)
            self.assertNotIn("UNIQUE PRD BODY SHOULD NOT BE INLINED", rendered)

            ref_ids = [ref["id"] for ref in packet["reference_index"]]
            self.assertEqual(ref_ids, ["pr_contract", "prd"])
            self.assertNotIn("coder_playbook", ref_ids)

if __name__ == '__main__':
    unittest.main()
