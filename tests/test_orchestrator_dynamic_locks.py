import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Add scripts directory to path to allow import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import orchestrator

def test_orchestrator_dynamic_locks():
    """
    Test Case 2: Run orchestrator setup without a global OpenClaw workspace and assert 
    that the concurrency locks are created in the system temp folder 
    (e.g. via tempfile.gettempdir()).
    """
    projects = ["mock_project_1", "mock_project_2"]
    
    # Mock fcntl and os.open to avoid actual file locking conflicts during testing
    with tempfile.TemporaryDirectory() as mock_workdir:
        with patch("orchestrator.os.open") as mock_open, \
             patch("orchestrator.fcntl.flock") as mock_flock:
            
            mock_open.return_value = 999  # Dummy file descriptor
            
            acquired_locks, fds = orchestrator.acquire_global_locks(projects, mock_workdir)
            
            expected_lock_dir = os.path.join(tempfile.gettempdir(), "openclaw_locks")
            
            # Verify the lock files are created in the correct temp directory
            assert len(acquired_locks) == 2
            for i, project in enumerate(projects):
                expected_lock_path = os.path.join(expected_lock_dir, f"{project}.lock")
                assert acquired_locks[i] == expected_lock_path
                
                # Verify os.open was called with the correct path
                mock_open.assert_any_call(expected_lock_path, os.O_CREAT | os.O_RDWR)
