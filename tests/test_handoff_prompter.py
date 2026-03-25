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
        self.assertIn("The pipeline has finished. You must now: 1. Close the PRD. 2. Close the Issue. 3. Update STATE.md.", prompt)

    def test_dirty_workspace(self):
        prompt = HandoffPrompter.get_prompt("dirty_workspace")
        self.assertIn("[FATAL_STARTUP]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Workspace is dirty. You must run `git commit` or `git stash` to clean the workspace before proceeding.", prompt)

    def test_planner_failure(self):
        prompt = HandoffPrompter.get_prompt("planner_failure")
        self.assertIn("[FATAL_PLANNER]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Planner failed. You must read planner logs and refine the PRD.", prompt)

    def test_git_checkout_error(self):
        prompt = HandoffPrompter.get_prompt("git_checkout_error")
        self.assertIn("[FATAL_GIT]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Git checkout failed. You must run `git branch -D` and `git clean -fd` to resolve the state.", prompt)

    def test_dead_end(self):
        prompt = HandoffPrompter.get_prompt("dead_end")
        self.assertIn("[FATAL_ESCALATION]", prompt)
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Dead End reached. You must read `Review_Report.md` and alert the Boss explicitly.", prompt)

    def test_unknown_condition(self):
        prompt = HandoffPrompter.get_prompt("unknown_condition")
        self.assertIn("[ACTION REQUIRED FOR MANAGER]", prompt)
        self.assertIn("Unknown exit condition.", prompt)

if __name__ == "__main__":
    unittest.main()
