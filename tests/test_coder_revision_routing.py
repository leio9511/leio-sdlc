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


RAW_REVIEW_JSON = '{"status":"NEEDS_FIX","findings":[{"id":"F1","message":"Patch the exact bug."}]}'
REVISION_RULE = "Do not restart problem-solving from scratch. Modify the existing implementation to satisfy the reviewer findings."
RECOVERY_WARNING = "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts."


class TestCoderRevisionRouting(unittest.TestCase):
    def _write_common_files(self, tmp_dir):
        pr_file = os.path.join(tmp_dir, "PR_001.md")
        prd_file = os.path.join(tmp_dir, "PRD.md")
        playbook_file = os.path.join(tmp_dir, "coder_playbook.md")
        feedback_file = os.path.join(tmp_dir, "review_report.json")
        Path(pr_file).write_text("PR contract", encoding="utf-8")
        Path(prd_file).write_text("PRD", encoding="utf-8")
        Path(playbook_file).write_text("Playbook", encoding="utf-8")
        Path(feedback_file).write_text(RAW_REVIEW_JSON, encoding="utf-8")
        return pr_file, prd_file, playbook_file, feedback_file

    @patch('spawn_coder.get_current_branch', return_value='feature/revision-routing')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.invoke_agent')
    def test_feedback_with_existing_session_sends_delta_revision_prompt(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="existing-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file, feedback_file = self._write_common_files(tmp_dir)
            session_file = os.path.join(tmp_dir, ".coder_session")
            Path(session_file).write_text("existing-session", encoding="utf-8")

            is_existing, key = spawn_coder.handle_feedback_routing(
                tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, feedback_file, "PR_001"
            )

            self.assertTrue(is_existing)
            self.assertEqual(key, "existing-session")
            self.assertEqual(Path(session_file).read_text(encoding="utf-8"), "existing-session")
            mock_invoke.assert_called_once()
            prompt = mock_invoke.call_args[0][0]
            self.assertEqual(mock_invoke.call_args[1]["session_key"], "existing-session")
            self.assertIn("# REVIEW REPORT JSON", prompt)
            self.assertIn(RAW_REVIEW_JSON, prompt)
            self.assertIn(REVISION_RULE, prompt)
            self.assertIn("not a fresh task", prompt.lower())
            self.assertIn("Existing branch state", prompt)
            self.assertNotIn("# REFERENCE INDEX", prompt)

    @patch('spawn_coder.get_current_branch', return_value='feature/revision-bootstrap')
    @patch('spawn_coder.get_latest_commit_hash', return_value='def456')
    @patch('spawn_coder.invoke_agent')
    def test_feedback_without_session_spawns_revision_bootstrap_recovery_prompt(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="new-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file, feedback_file = self._write_common_files(tmp_dir)

            is_existing, key = spawn_coder.handle_feedback_routing(
                tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, feedback_file, "PR_001"
            )

            self.assertFalse(is_existing)
            self.assertEqual(key, "new-session")
            prompt = mock_invoke.call_args[0][0]
            self.assertIn(RECOVERY_WARNING, prompt)
            self.assertIn("# REVIEW REPORT JSON", prompt)
            self.assertIn(RAW_REVIEW_JSON, prompt)
            self.assertIn(os.path.abspath(pr_file), prompt)
            self.assertIn(os.path.abspath(prd_file), prompt)
            self.assertIn(os.path.abspath(playbook_file), prompt)
            self.assertIn(os.path.abspath(feedback_file), prompt)
            self.assertIn("feature/revision-bootstrap", prompt)
            self.assertIn("def456", prompt)
            self.assertEqual(Path(os.path.join(tmp_dir, ".coder_session")).read_text(encoding="utf-8"), "new-session")

    @patch('spawn_coder.get_current_branch', return_value='feature/revision-routing')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.invoke_agent')
    def test_revision_debug_artifacts_are_mode_scoped_and_non_overwriting(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="existing-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file, feedback_file = self._write_common_files(tmp_dir)
            Path(os.path.join(tmp_dir, ".coder_session")).write_text("existing-session", encoding="utf-8")

            spawn_coder.handle_feedback_routing(tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, feedback_file, "PR_001")
            first_prompt = mock_invoke.call_args[0][0]
            Path(feedback_file).write_text('{"status":"NEEDS_FIX","findings":[{"id":"F2","message":"Second cycle."}]}', encoding="utf-8")
            spawn_coder.handle_feedback_routing(tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, feedback_file, "PR_001")
            second_prompt = mock_invoke.call_args[0][0]

            first_artifact = Path(tmp_dir) / "coder_debug" / "revision_001" / "rendered_prompt.txt"
            second_artifact = Path(tmp_dir) / "coder_debug" / "revision_002" / "rendered_prompt.txt"
            self.assertTrue(first_artifact.exists())
            self.assertTrue(second_artifact.exists())
            self.assertEqual(first_artifact.read_text(encoding="utf-8"), first_prompt)
            self.assertEqual(second_artifact.read_text(encoding="utf-8"), second_prompt)
            self.assertIn("F1", first_artifact.read_text(encoding="utf-8"))
            self.assertIn("F2", second_artifact.read_text(encoding="utf-8"))

    @patch('spawn_coder.get_current_branch', return_value='feature/revision-bootstrap')
    @patch('spawn_coder.get_latest_commit_hash', return_value='def456')
    @patch('spawn_coder.invoke_agent')
    def test_revision_bootstrap_debug_artifacts_are_mode_scoped(self, mock_invoke, mock_commit, mock_branch):
        mock_invoke.return_value = AgentResult(session_key="new-session", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file, prd_file, playbook_file, feedback_file = self._write_common_files(tmp_dir)
            spawn_coder.handle_feedback_routing(tmp_dir, tmp_dir, pr_file, prd_file, playbook_file, feedback_file, "PR_001")

            bootstrap_dir = Path(tmp_dir) / "coder_debug" / "revision_bootstrap_001"
            packet_file = bootstrap_dir / "startup_packet.json"
            prompt_file = bootstrap_dir / "rendered_prompt.txt"
            self.assertTrue(packet_file.exists())
            self.assertTrue(prompt_file.exists())
            packet = json.loads(packet_file.read_text(encoding="utf-8"))
            prompt = prompt_file.read_text(encoding="utf-8")
            self.assertEqual(packet["mode"], "revision_bootstrap")
            self.assertEqual(packet["lifecycle"], "recovery_bootstrap_continuation")
            self.assertFalse(packet["continuation_semantics"]["fresh_task"])
            self.assertIn(RECOVERY_WARNING, prompt)
            self.assertIn(RAW_REVIEW_JSON, prompt)


if __name__ == '__main__':
    unittest.main()
