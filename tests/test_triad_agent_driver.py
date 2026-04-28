import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import shutil

# Correct paths before any other imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
# Try to find pm-skill scripts directory
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PM_SKILL_SCRIPTS = os.path.join(WORKSPACE_ROOT, 'skills/pm-skill/scripts')
if os.path.exists(PM_SKILL_SCRIPTS):
    sys.path.insert(0, PM_SKILL_SCRIPTS)
else:
    # Fallback to relative if somehow root is different
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'skills/pm-skill/scripts')))

from agent_driver import build_prompt, AgentResult

class TestAgentDriverTriad(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.original_test_mode = os.environ.get("SDLC_TEST_MODE")
        os.environ["SDLC_TEST_MODE"] = "false"

    def tearDown(self):
        shutil.rmtree(self.workdir)
        if self.original_test_mode is not None:
            os.environ["SDLC_TEST_MODE"] = self.original_test_mode
        else:
            del os.environ["SDLC_TEST_MODE"]

    @patch('spawn_coder.invoke_agent')
    @patch('subprocess.check_output')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_coder_payload_injection(self, mock_setup_key, mock_check_output, mock_agent_call):
        import spawn_coder
        mock_check_output.return_value = "feature-branch\n"
        mock_agent_call.return_value = AgentResult(session_key='subtask-123', stdout='dummy')

        pr_file = os.path.join(self.workdir, "PR_001.md")
        prd_file = os.path.join(self.workdir, "PRD.md")
        with open(pr_file, "w") as f:
            f.write("mock_pr_content")
        with open(prd_file, "w") as f:
            f.write("mock_prd_content")

        test_args = ["spawn_coder.py", "--pr-file", pr_file, "--prd-file", prd_file, "--workdir", self.workdir, "--enable-exec-from-workspace"]
        with patch.object(sys, 'argv', test_args):
            spawn_coder.main()

        self.assertTrue(mock_agent_call.called, "invoke_agent was not called")
        args, kwargs = mock_agent_call.call_args
        self.assertTrue(args[0].startswith("# EXECUTION CONTRACT"))
        self.assertIn(os.path.abspath(pr_file), args[0])
        self.assertIn(os.path.abspath(prd_file), args[0])
        self.assertIn("coder_playbook", args[0])
        self.assertNotIn("mock_pr_content", args[0])
        self.assertNotIn("mock_prd_content", args[0])
        mock_setup_key.assert_called()

    @patch('spawn_coder.invoke_agent')
    @patch('subprocess.check_output')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_coder_feedback_injection(self, mock_setup_key, mock_check_output, mock_agent_call):
        import spawn_coder
        mock_check_output.return_value = "feature-branch\n"
        mock_agent_call.return_value = AgentResult(session_key='subtask-123', stdout='dummy')

        pr_file = os.path.join(self.workdir, "PR_001.md")
        prd_file = os.path.join(self.workdir, "PRD.md")
        feedback_file = os.path.join(self.workdir, "review_report.json")

        with open(pr_file, "w") as f:
            f.write("mock_pr_content")
        with open(prd_file, "w") as f:
            f.write("mock_prd_content")
        with open(feedback_file, "w") as f:
            f.write('```json\n{"overall_assessment": "NEEDS_ATTENTION", "findings": [{"description": "raw JSON test"}]}\n```')

        test_args = ["spawn_coder.py", "--pr-file", pr_file, "--prd-file", prd_file, "--workdir", self.workdir, "--feedback-file", feedback_file, "--enable-exec-from-workspace"]
        with patch.object(sys, 'argv', test_args):
            spawn_coder.main()

        self.assertTrue(mock_agent_call.called, "invoke_agent was not called")
        args, kwargs = mock_agent_call.call_args
    
        # Verify that the envelope references the feedback artifact instead of inlining it
        self.assertNotIn("```json", args[0])
        self.assertNotIn('"overall_assessment": "NEEDS_ATTENTION"', args[0])
        self.assertIn(feedback_file, args[0])
        self.assertNotIn('"description": "raw JSON test"', args[0])
        mock_setup_key.assert_called()

    def test_build_prompt_resolves_correctly(self):
        prompt = build_prompt("arbitrator", workdir="/tmp/test", pr_file="test_pr.md", pr_content="mock_pr_content", diff_file="dummy.diff", review_report_path="report.json", run_dir="run")

        self.assertNotEqual(prompt, "")
        self.assertIn("/tmp/test", prompt)
        self.assertIn("mock_pr_content", prompt)
        self.assertIn("ATTENTION:", prompt)
        
        coder_prompt = build_prompt("coder")
        self.assertEqual(coder_prompt, "__DEPRECATED__ use envelope_assembler.py — see spawn_coder.py")


    @patch('spawn_planner.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_planner_payload_injection(self, mock_setup_key, mock_invoke_agent):
        import spawn_planner
        mock_invoke_agent.return_value = AgentResult(session_key='subtask-planner', stdout='dummy')

        prd_file = os.path.join(self.workdir, "PRD.md")
        with open(prd_file, "w") as f:
            f.write("mock_prd_content_for_planner")

        test_args = ["spawn_planner.py", "--prd-file", prd_file, "--workdir", self.workdir, "--enable-exec-from-workspace"]
        with patch.object(sys, 'argv', test_args):
            spawn_planner.main()

        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for planner")
        args, kwargs = mock_invoke_agent.call_args
        self.assertIn(prd_file, args[0])
        self.assertEqual(kwargs.get("role"), "planner")
        self.assertTrue(kwargs.get("session_key", "").startswith("subtask-"))
        mock_setup_key.assert_called()

    @patch('spawn_reviewer.invoke_agent')
    @patch('subprocess.run')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_reviewer_payload_injection(self, mock_setup_key, mock_run, mock_invoke_agent):
        import spawn_reviewer

        def mock_reviewer_invoke(*args, **kwargs):
            # simulate agent writing the artifact
            with open(os.path.join(self.workdir, "review_report.json"), "w") as f:
                f.write('{"overall_assessment": "EXCELLENT", "executive_summary": "mock summary", "findings": []}')
            return AgentResult(session_key='subtask-reviewer', stdout='dummy')
        mock_invoke_agent.side_effect = mock_reviewer_invoke

        pr_file = os.path.join(self.workdir, "PR_001.md")
        with open(pr_file, "w") as f:
            f.write("mock_pr_content_for_reviewer")

        test_args = ["spawn_reviewer.py", "--pr-file", pr_file, "--diff-target", "master", "--workdir", self.workdir, "--out-file", "review_report.json", "--run-dir", self.workdir, "--enable-exec-from-workspace"]

        dummy_diff = os.path.join(self.workdir, "dummy.diff")
        with open(dummy_diff, "w") as f:
            f.write("mock diff")

        with patch.object(sys, 'argv', test_args):
            spawn_reviewer.main()

        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for reviewer")
        args, kwargs = mock_invoke_agent.call_args
        self.assertIn("# REFERENCE INDEX", args[0])
        self.assertIn("diff", args[0])
        self.assertEqual(kwargs.get("role"), "reviewer")
        mock_setup_key.assert_called()


    @patch('spawn_arbitrator.invoke_agent')
    @patch('subprocess.run')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_arbitrator_payload_injection(self, mock_setup_key, mock_run, mock_invoke_agent):
        import spawn_arbitrator

        def mock_arbitrator_invoke(*args, **kwargs):
            # simulate agent writing the artifact
            with open(os.path.join(self.workdir, "arbitration_report.txt"), "w") as f:
                f.write("mock arbitration report content")
            return AgentResult(session_key='subtask-arbitrator', stdout='dummy')
        mock_invoke_agent.side_effect = mock_arbitrator_invoke

        pr_file = os.path.join(self.workdir, "PR_001.md")
        with open(pr_file, "w") as f:
            f.write("mock_pr_content_for_arbitrator")

        test_args = ["spawn_arbitrator.py", "--pr-file", pr_file, "--diff-target", "master", "--workdir", self.workdir, "--enable-exec-from-workspace"]

        dummy_diff = os.path.join(self.workdir, "dummy.diff")
        with open(dummy_diff, "w") as f:
            f.write("mock diff")

        with patch.object(sys, 'argv', test_args):
            spawn_arbitrator.main()

        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for arbitrator")
        args, kwargs = mock_invoke_agent.call_args
        self.assertIn("mock_pr_content_for_arbitrator", args[0])
        self.assertEqual(kwargs.get("role"), "arbitrator")
        mock_setup_key.assert_called()

    @patch('spawn_manager.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_manager_payload_injection(self, mock_setup_key, mock_invoke_agent):
        import spawn_manager
        mock_invoke_agent.return_value = AgentResult(session_key='subtask-manager', stdout='dummy')

        test_args = ["spawn_manager.py", "--job-dir", "/tmp/job", "--workdir", self.workdir, "--enable-exec-from-workspace"]

        with patch.object(sys, 'argv', test_args):
            spawn_manager.main()

        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for manager")
        args, kwargs = mock_invoke_agent.call_args
        self.assertEqual(kwargs.get("role"), "manager")
        mock_setup_key.assert_called()




    def test_spawn_scripts_keep_runtime_aware_prompt_resolution(self):
        from agent_driver import build_prompt

        prompt = build_prompt("manager", workdir="/tmp/test", job_dir="/tmp/job", skill_text="mock_skill_text")

        self.assertNotEqual(prompt, "")
        self.assertIn("/tmp/test", prompt)

if __name__ == '__main__':
    unittest.main()
