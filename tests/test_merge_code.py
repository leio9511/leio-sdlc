import unittest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import merge_code

class TestMergeCode(unittest.TestCase):
    def test_extract_json_from_llm_response_valid_markdown(self):
        content = '```json\n{"overall_assessment": "EXCELLENT", "findings": []}\n```'
        result = merge_code.extract_json_from_llm_response(content)
        self.assertEqual(result, {"overall_assessment": "EXCELLENT", "findings": []})

    def test_extract_json_from_llm_response_malformed(self):
        content = '```json\n{"overall_assessment": "EXCELLENT", "findings": [\n```'
        result = merge_code.extract_json_from_llm_response(content)
        self.assertIsNone(result)

    def test_parse_review_verdict_approved(self):
        content = '```json\n{"status": "APPROVED"}\n```'
        self.assertEqual(merge_code.parse_review_verdict(content), "APPROVED")

    def test_parse_review_verdict_action_required(self):
        content = '{"status": "ACTION_REQUIRED", "comments": "Fix it"}'
        self.assertEqual(merge_code.parse_review_verdict(content), "ACTION_REQUIRED")

    def test_parse_review_verdict_invalid(self):
        content = 'This is just some text with no JSON'
        self.assertIsNone(merge_code.parse_review_verdict(content))

if __name__ == '__main__':
    unittest.main()
