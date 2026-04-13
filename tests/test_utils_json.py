import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from utils_json import extract_and_parse_json

def test_extract_pure_json():
    text = '{"status": "APPROVED", "reason": "All good"}'
    result = extract_and_parse_json(text)
    assert result == {"status": "APPROVED", "reason": "All good"}

def test_extract_markdown_json():
    text = """
    Here is the review report:
    ```json
    {
        "status": "REJECTED",
        "reason": "Missing tests"
    }
    ```
    Please fix the issues.
    """
    result = extract_and_parse_json(text)
    assert result == {"status": "REJECTED", "reason": "Missing tests"}

def test_extract_invalid_json():
    text = "This is just some text without JSON"
    with pytest.raises(ValueError, match="Could not extract valid JSON"):
        extract_and_parse_json(text)
