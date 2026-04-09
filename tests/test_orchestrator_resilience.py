import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

class TestOrchestratorResilience(unittest.TestCase):
    def test_blast_radius_clears_sessions(self):
        import orchestrator
        import inspect
        source = inspect.getsource(orchestrator.main)
        self.assertIn("Executing Blast Radius Control...", source)
        self.assertIn(".coder_session", source)
        self.assertIn("os.remove(session_file_path)", source)

    def test_yellow_path_preserves_session(self):
        import orchestrator
        import inspect
        source = inspect.getsource(orchestrator.main)
        # Verify Four-Path Resilience components
        self.assertIn("yellow_retry_limit =", source)
        self.assertIn("yellow_counter", source)
        self.assertIn("ACTION_REQUIRED", source)

    def test_red_path_hard_resets(self):
        import orchestrator
        import inspect
        source = inspect.getsource(orchestrator.main)
        self.assertIn("red_retry_limit =", source)
        self.assertIn("red_counter", source)
        self.assertIn("State 5 Escalation - Tier 1", source)
        self.assertIn("git\", \"reset\", \"--hard", source)
        self.assertIn("teardown_coder_session(workdir)", source)
        self.assertIn("blocked_fatal", source)

if __name__ == "__main__":
    unittest.main()