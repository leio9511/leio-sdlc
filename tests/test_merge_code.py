import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import merge_code

class TestMergeCode(unittest.TestCase):
    def test_parse_review_verdict_approved(self):
        content = '```json\n{"overall_assessment": "EXCELLENT"}\n```'
        self.assertEqual(merge_code.parse_review_verdict(content), "APPROVED")

        content2 = '{"overall_assessment": "GOOD_WITH_MINOR_SUGGESTIONS"}'
        self.assertEqual(merge_code.parse_review_verdict(content2), "APPROVED")

    def test_parse_review_verdict_action_required(self):
        content = '{"overall_assessment": "NEEDS_ATTENTION", "findings": []}'
        self.assertEqual(merge_code.parse_review_verdict(content), "ACTION_REQUIRED")

        content2 = '```json\n{"overall_assessment": "NEEDS_IMMEDIATE_REWORK"}\n```'
        self.assertEqual(merge_code.parse_review_verdict(content2), "ACTION_REQUIRED")

    def test_parse_review_verdict_malformed(self):
        content = 'This is just some text with no JSON'
        self.assertIsNone(merge_code.parse_review_verdict(content))
        
        content2 = '```json\n{"overall_assessment": "EXCELLENT", "findings": [\n```'
        self.assertIsNone(merge_code.parse_review_verdict(content2))

    @patch("merge_code.run_runtime_git")
    @patch("merge_code.os.path.isfile", return_value=True)
    @patch("builtins.open")
    def test_merge_code_uses_runtime_helper_with_merge_code_role(self, mock_open, mock_isfile, mock_run_runtime_git):
        mock_open.return_value.__enter__.return_value.read.return_value = '{"overall_assessment": "EXCELLENT"}'
        mock_run_runtime_git.return_value = MagicMock(stdout="merged\n")

        with patch.dict(os.environ, {"SDLC_TEST_MODE": ""}, clear=False):
            with patch.object(sys, "argv", ["merge_code.py", "--branch", "feature/test", "--review-file", "review.json"]):
                merge_code.main()

        mock_run_runtime_git.assert_called_once_with(
            "merge_code",
            ["merge", "feature/test"],
            check=True,
            text=True,
            capture_output=True,
        )

if __name__ == '__main__':
    unittest.main()
