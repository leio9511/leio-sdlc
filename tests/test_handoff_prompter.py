import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
from handoff_prompter import HandoffPrompter

class TestHandoffPrompter(unittest.TestCase):
    def test_happy_path(self):
        prompt = HandoffPrompter.get_prompt("happy_path")
        self.assertIn("[SUCCESS_HANDOFF]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("The pipeline has finished. You must now: 1. Update PRD status.", prompt)

    def test_dirty_workspace(self):
        prompt = HandoffPrompter.get_prompt("dirty_workspace")
        self.assertIn("[FATAL_STARTUP]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Workspace is dirty.", prompt)

    def test_planner_failure(self):
        prompt = HandoffPrompter.get_prompt("planner_failure")
        self.assertIn("[FATAL_PLANNER]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Planner failed.", prompt)

    def test_git_checkout_error(self):
        prompt = HandoffPrompter.get_prompt("git_checkout_error")
        self.assertIn("[FATAL_GIT]", prompt)
        self.assertIn("Git checkout failed. Workspace preserved.", prompt)

    def test_dead_end(self):
        prompt = HandoffPrompter.get_prompt("dead_end")
        self.assertIn("[FATAL_ESCALATION]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Dead End reached. You MUST read `review_report.json` (located in the current job directory)", prompt)

    def test_unknown_condition(self):
        prompt = HandoffPrompter.get_prompt("unknown_condition")
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Unknown exit condition.", prompt)

    def test_prompt_template_injection(self):
        import config
        prompt = HandoffPrompter.get_prompt("happy_path")
        self.assertNotIn("{SDLC_SKILLS_ROOT}", prompt)
        self.assertIn(config.SDLC_SKILLS_ROOT, prompt)
        self.assertIn("issue_tracker/scripts/issues.py", prompt)

    def test_handoff_prompter_assertions_fixed(self):
        import config
        prompt = HandoffPrompter.get_prompt("git_checkout_error")
        self.assertNotIn("{SDLC_SKILLS_ROOT}", prompt)
        self.assertIn(config.SDLC_SKILLS_ROOT, prompt)
        self.assertIn("leio-sdlc/scripts/orchestrator.py", prompt)

if __name__ == "__main__":
    unittest.main()

    def test_handoff_prompter_uses_runtime_dir(self):
        import config
        from unittest.mock import patch
        
        custom_dir = "/opt/custom_sdlc_runtime"
        
        # We need to patch config.SDLC_RUNTIME_DIR to simulate an override
        with patch.object(config, 'SDLC_RUNTIME_DIR', custom_dir, create=True):
            prompt = HandoffPrompter.get_prompt("startup_validation_failed")
            self.assertNotIn("{SDLC_RUNTIME_DIR}", prompt)
            self.assertNotIn("{SDLC_SKILLS_ROOT}", prompt)
            self.assertIn(custom_dir, prompt)
