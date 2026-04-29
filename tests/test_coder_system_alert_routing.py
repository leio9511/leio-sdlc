import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import spawn_coder
from agent_driver import AgentResult

SYSTEM_ALERT_TEXT = "git dirty\nerror: preflight failed"
SYSTEM_ALERT_CONTINUATION_RULE = "Do not re-plan the whole PR. Fix the exact operational failure shown below, rerun validation, and continue from the current branch state."
RECOVERY_WARNING = "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts."

class TestCoderSystemAlertRouting(unittest.TestCase):
    def _write_common_files(self, tmp_dir):
        pr_file = os.path.join(tmp_dir, "PR_001.md")
        prd_file = os.path.join(tmp_dir, "PRD.md")
        playbook_file = os.path.join(tmp_dir, "coder_playbook.md")
        Path(pr_file).write_text("PR contract", encoding="utf-8")
        Path(prd_file).write_text("PRD", encoding="utf-8")
        Path(playbook_file).write_text("Playbook", encoding="utf-8")
        return pr_file, prd_file, playbook_file

    @patch('spawn_coder.get_current_branch', return_value='feature/system-alert-routing')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.invoke_agent')
    def test_system_alert_with_existing_session_sends_operational_delta_prompt(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="existing-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file = self._write_common_files(tmp_dir)
            session_file = os.path.join(tmp_dir, ".coder_session")
            Path(session_file).write_text("existing-session", encoding="utf-8")

            is_existing, key = spawn_coder.handle_system_alert_routing(
                tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, SYSTEM_ALERT_TEXT, "PR_001"
            )

            self.assertTrue(is_existing)
            self.assertEqual(key, "existing-session")
            self.assertEqual(Path(session_file).read_text(encoding="utf-8"), "existing-session")
            mock_invoke.assert_called_once()
            prompt = mock_invoke.call_args[0][0]
            self.assertEqual(mock_invoke.call_args[1]["session_key"], "existing-session")
            self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt)
            self.assertIn(SYSTEM_ALERT_TEXT, prompt)
            self.assertIn(SYSTEM_ALERT_CONTINUATION_RULE, prompt)
            self.assertNotIn("# REFERENCE INDEX", prompt)

    @patch('spawn_coder.get_current_branch', return_value='feature/system-alert-bootstrap')
    @patch('spawn_coder.get_latest_commit_hash', return_value='def456')
    @patch('spawn_coder.invoke_agent')
    def test_system_alert_without_session_spawns_recovery_prompt(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="new-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file = self._write_common_files(tmp_dir)

            is_existing, key = spawn_coder.handle_system_alert_routing(
                tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, SYSTEM_ALERT_TEXT, "PR_001"
            )

            self.assertFalse(is_existing)
            self.assertEqual(key, "new-session")
            prompt = mock_invoke.call_args[0][0]
            self.assertIn(RECOVERY_WARNING, prompt)
            self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt)
            self.assertIn(SYSTEM_ALERT_TEXT, prompt)
            self.assertIn(os.path.abspath(pr_file), prompt)
            self.assertIn(os.path.abspath(prd_file), prompt)
            self.assertIn(os.path.abspath(playbook_file), prompt)
            self.assertIn("feature/system-alert-bootstrap", prompt)
            self.assertIn("def456", prompt)
            self.assertEqual(Path(os.path.join(tmp_dir, ".coder_session")).read_text(encoding="utf-8"), "new-session")

    @patch('spawn_coder.get_current_branch', return_value='feature/system-alert-routing')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.invoke_agent')
    def test_system_alert_debug_artifacts_are_mode_scoped_and_non_overwriting(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="existing-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file = self._write_common_files(tmp_dir)
            Path(os.path.join(tmp_dir, ".coder_session")).write_text("existing-session", encoding="utf-8")

            spawn_coder.handle_system_alert_routing(tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, "alert 1", "PR_001")
            first_prompt = mock_invoke.call_args[0][0]
            spawn_coder.handle_system_alert_routing(tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, "alert 2", "PR_001")
            second_prompt = mock_invoke.call_args[0][0]

            first_artifact = Path(tmp_dir) / "coder_debug" / "system_alert_001" / "rendered_prompt.txt"
            second_artifact = Path(tmp_dir) / "coder_debug" / "system_alert_002" / "rendered_prompt.txt"
            self.assertTrue(first_artifact.exists())
            self.assertTrue(second_artifact.exists())
            self.assertEqual(first_artifact.read_text(encoding="utf-8"), first_prompt)
            self.assertEqual(second_artifact.read_text(encoding="utf-8"), second_prompt)
            self.assertIn("alert 1", first_artifact.read_text(encoding="utf-8"))
            self.assertIn("alert 2", second_artifact.read_text(encoding="utf-8"))

    def test_coder_playbook_documents_abcd_lifecycle_model(self):
        playbook_path = os.path.join(os.path.dirname(__file__), '..', 'playbooks', 'coder_playbook.md')
        content = Path(playbook_path).read_text(encoding="utf-8")
        self.assertIn("initial", content)
        self.assertIn("revision", content)
        self.assertIn("revision_bootstrap", content)
        self.assertIn("system_alert", content)
        self.assertIn("recovery-shaped full bootstrap", content)
        self.assertIn("same-session operational delta continuation", content)

if __name__ == '__main__':
    unittest.main()
