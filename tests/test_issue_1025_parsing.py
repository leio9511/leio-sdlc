import unittest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# We will need to mock components that orchestrator.py imports or uses
# For now, let's just test the parsing logic we intend to implement.

def parse_review_verdict(content):
    """
    Proposed implementation of the parsing logic.
    We look for a JSON block in the content.
    """
    # Simple regex to find JSON-like structure or just try to find the first '{' and last '}'
    try:
        # Try to find a JSON block between ```json and ```
        import re
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            return data.get("status")
        
        # Fallback: try to find any JSON-like object
        json_match = re.search(r'(\{.*?\})', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            return data.get("status")
    except (json.JSONDecodeError, AttributeError):
        pass
    
    # Fallback to old behavior if no valid JSON found? 
    # The PR contract says: "Do not use string matching for approval status."
    # So we should probably return None or raise error if JSON is missing/invalid.
    return None

class TestReviewParsing(unittest.TestCase):
    def test_json_approval(self):
        content = """
The changes look good.
```json
{"status": "APPROVED", "comments": "Passes all tests."}
```
"""
        self.assertEqual(parse_review_verdict(content), "APPROVED")

    def test_json_rejection(self):
        content = """
Issues found.
```json
{"status": "ACTION_REQUIRED", "comments": "Missing tests."}
```
"""
        self.assertEqual(parse_review_verdict(content), "ACTION_REQUIRED")

    def test_adversarial_rejection(self):
        # This is the core requirement: string [LGTM] inside comments of a rejection
        content = """
The Coder improperly included [LGTM] in their output. This is a violation.
```json
{"status": "ACTION_REQUIRED", "comments": "Found literal [LGTM] in code which is not allowed."}
```
"""
        # The old logic would see "[LGTM]" and approve.
        # Our new logic should see "ACTION_REQUIRED".
        self.assertEqual(parse_review_verdict(content), "ACTION_REQUIRED")

    def test_malformed_json(self):
        content = "This is not JSON [LGTM]"
        self.assertIsNone(parse_review_verdict(content))

if __name__ == '__main__':
    unittest.main()
