import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import os
import tempfile
import pytest
from scripts.utils_path import resolve_global_dir, get_canonical_job_dir
from scripts import config

def test_global_run_dir_resolves_tilde():
    """Test Case 1: GLOBAL_RUN_DIR='~/.sdlc' resolves to the absolute path under the user's actual home."""
    raw_path = "~/.sdlc"
    resolved = resolve_global_dir(raw_path)
    expected = os.path.abspath(os.path.expanduser(raw_path))
    assert resolved == expected
    assert "~" not in resolved
    # Ensure it's rooted at the user home
    assert resolved.startswith(os.path.expanduser("~"))

def test_orchestrator_cli_global_dir_resolves_tilde():
    """Test Case 2: orchestrator_cli_global_dir_resolves_tilde"""
    raw_path = "~/.sdlc_cli"
    resolved = resolve_global_dir(raw_path)
    expected = os.path.abspath(os.path.expanduser(raw_path))
    assert resolved == expected
    assert "~" not in resolved
    assert resolved.startswith(os.path.expanduser("~"))
