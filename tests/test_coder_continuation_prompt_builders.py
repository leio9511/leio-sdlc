import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from spawn_coder import (
    build_coder_revision_continuation_prompt,
    build_coder_revision_recovery_prompt,
    build_coder_system_alert_continuation_prompt,
    build_coder_system_alert_recovery_prompt,
)


REVISION_RULE = "Do not restart problem-solving from scratch. Modify the existing implementation to satisfy the reviewer findings."
ALERT_RULE = "Do not re-plan the whole PR. Fix the exact operational failure shown below, rerun validation, and continue from the current branch state."
RECOVERY_WARNING = "This is a recovery continuation, not a fresh task start. Existing branch state and current implementation are authoritative facts."


class TestCoderContinuationPromptBuilders(unittest.TestCase):
    def test_revision_continuation_prompt_inlines_raw_review_report(self):
        raw_review_json = '{"status":"needs_changes","findings":[{"id":"F1","message":"Fix branch context handling."}]}'

        prompt = build_coder_revision_continuation_prompt(
            workdir="/repo/workdir",
            pr_file="/runs/PR_001.md",
            prd_file="/docs/PRD.md",
            playbook_path="/skills/playbooks/coder_playbook.md",
            review_report_json=raw_review_json,
            feedback_file="/runs/review_report.json",
        )

        self.assertIn("# REVIEW REPORT JSON", prompt)
        self.assertIn(raw_review_json, prompt)
        self.assertIn(REVISION_RULE, prompt)
        self.assertNotIn("# REFERENCE INDEX", prompt)
        self.assertIn("/repo/workdir", prompt)
        self.assertIn("/runs/review_report.json", prompt)

    def test_revision_recovery_prompt_is_recovery_specific_not_blank_slate(self):
        raw_review_json = '{"status":"needs_changes","summary":"Current code missed validation."}'

        prompt = build_coder_revision_recovery_prompt(
            workdir="/repo/workdir",
            pr_file="/runs/PR_001.md",
            prd_file="/docs/PRD.md",
            playbook_path="/skills/playbooks/coder_playbook.md",
            review_report_json=raw_review_json,
            feedback_file="/runs/review_report.json",
            current_branch="feature/continuation-prompts",
            latest_commit_hash="abc1234",
        )

        self.assertIn(RECOVERY_WARNING, prompt)
        self.assertIn("feature/continuation-prompts", prompt)
        self.assertIn("abc1234", prompt)
        self.assertIn("# REVIEW REPORT JSON", prompt)
        self.assertIn(raw_review_json, prompt)
        self.assertIn("current implementation is authoritative", prompt)
        self.assertNotIn("blank-slate", prompt.lower())

    def test_system_alert_continuation_prompt_inlines_exact_alert(self):
        alert = "preflight failed: tests/test_example.py::test_case assertion mismatch"

        prompt = build_coder_system_alert_continuation_prompt(
            workdir="/repo/workdir",
            pr_file="/runs/PR_001.md",
            prd_file="/docs/PRD.md",
            playbook_path="/skills/playbooks/coder_playbook.md",
            system_alert=alert,
        )

        self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt)
        self.assertIn(alert, prompt)
        self.assertIn(ALERT_RULE, prompt)
        self.assertNotIn("# REFERENCE INDEX", prompt)

    def test_system_alert_recovery_prompt_remains_tightly_scoped(self):
        alert = "git status dirty after validation: modified scripts/spawn_coder.py"

        prompt = build_coder_system_alert_recovery_prompt(
            workdir="/repo/workdir",
            pr_file="/runs/PR_001.md",
            prd_file="/docs/PRD.md",
            playbook_path="/skills/playbooks/coder_playbook.md",
            system_alert=alert,
            current_branch="feature/system-alert",
            latest_commit_hash="def5678",
        )

        self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt)
        self.assertIn(alert, prompt)
        self.assertIn(RECOVERY_WARNING, prompt)
        self.assertIn("feature/system-alert", prompt)
        self.assertIn("def5678", prompt)
        self.assertIn("corrective action", prompt.lower())
        self.assertNotIn("# REFERENCE INDEX", prompt)
        self.assertNotIn("# EXECUTION CONTRACT", prompt)


if __name__ == '__main__':
    unittest.main()
