import sys
import os
import unittest
from unittest.mock import patch

# Add scripts directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

class TestOrchestratorCLI(unittest.TestCase):
    @patch("sys.argv", ["orchestrator.py", "--prd-file", "dummy.md"])
    def test_missing_workdir_exits(self):
        with self.assertRaises(SystemExit) as cm:
            import orchestrator
            orchestrator.main()
        self.assertNotEqual(cm.exception.code, 0)

if __name__ == "__main__":
    unittest.main()
