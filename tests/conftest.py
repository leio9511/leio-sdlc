import os
import pytest

PROJECT_ROOT = os.getcwd()

@pytest.fixture(autouse=True)
def global_restore_cwd():
    """Globally restore the current working directory after each test."""
    try:
        original_cwd = os.getcwd()
    except FileNotFoundError:
        original_cwd = PROJECT_ROOT
        
    yield
    try:
        os.chdir(original_cwd)
    except FileNotFoundError:
        os.chdir(PROJECT_ROOT)
