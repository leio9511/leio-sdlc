import os
import sys
import pytest
from unittest.mock import patch

# Add scripts directory to path to allow import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "skills", "pm-skill", "scripts")))

import init_prd

import tempfile

def test_init_prd_custom_workdir(capsys):
    with tempfile.TemporaryDirectory() as mock_workdir:
        with patch.object(sys, "argv", ["init_prd.py", "--project", "test_project", "--title", "test_title", "--workdir", mock_workdir]):
            try:
                init_prd.main()
            except SystemExit as e:
                assert e.code == 0
            
            captured = capsys.readouterr()
            assert "[SUCCESS]" in captured.out
            
            # Assert PRD is successfully created in /tmp/mock_app/docs/PRDs/
            expected_prd_path = os.path.join(mock_workdir, "docs", "PRDs", "PRD_test_title.md")
            assert os.path.exists(expected_prd_path), f"PRD not created at {expected_prd_path}"
