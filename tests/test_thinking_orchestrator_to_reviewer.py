"""Mock-based integration tests for orchestrator --thinking propagation to spawn_reviewer.

Validates that --thinking is propagated from orchestrator CLI to the initial
spawn_reviewer dpopen call (state 4).  Covers default 'high', explicit values,
and confirms that the reviewer retry path is NOT modified.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


class TestThinkingOrchestratorToReviewer(unittest.TestCase):
    """Integration tests for orchestrator --thinking → spawn_reviewer (initial) propagation."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_base_argv(self, workdir, global_dir, **kwargs):
        """Build sys.argv list for orchestrator.main() with common required args."""
        argv = [
            "orchestrator.py",
            "--enable-exec-from-workspace",
            "--workdir", workdir,
            "--prd-file", "dummy_prd.md",
            "--force-replan", kwargs.get("force_replan", "false"),
            "--channel", "test-channel",
            "--global-dir", global_dir,
        ]
        thinking = kwargs.get("thinking")
        if thinking is not None:
            argv.extend(["--thinking", thinking])
        return argv

    def _get_job_dir(self, workdir, global_dir, prd_filename="dummy_prd.md"):
        """Compute the job_dir the orchestrator will construct internally."""
        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name, _ = os.path.splitext(prd_filename)
        return os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))

    def _setup_full_pipeline_mocks(self, mocks, job_dir, base_name):
        """Configure mocks for full pipeline so orchestrator reaches State 4
        (reviewer spawn) and then exits.

        glob side_effect: returns [PR_file] → state machine enters state 3 (coder),
        then returns [PR_file] again → state machine enters state 4 (reviewer),
        then returns [] after reviewer spawn → avoids infloop.
        """
        pr_file = os.path.join(job_dir, f"{base_name}.md")
        os.makedirs(job_dir, exist_ok=True)
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")

        glob_call_count = [0]

        def glob_side_effect(pathname, **kwargs):
            glob_call_count[0] += 1
            if "*.md" in pathname or "PR_*.md" in pathname or "PRD_*.md" in pathname:
                if glob_call_count[0] <= 10:
                    return [pr_file]
            return []

        mocks["glob"].side_effect = glob_side_effect

        # dpopen: always succeeds
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mocks["dpopen"].return_value = mock_proc

        # classify_coder_null_output: returns non-null (coders produce work)
        mocks["classify_null"].return_value = (False, "", "deadbeef")
        # extract_json: returns APPROVED verdict so we advance past state 4
        mocks["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

        # drun – handle git ops and merge_code
        def drun_side_effect(cmd, *args, **kwargs):
            res = MagicMock()
            res.stdout = ""
            res.returncode = 0
            if isinstance(cmd, list):
                cmd_str = str(cmd)
                if "branch" in cmd_str:
                    res.stdout = "main\n"
                if "git" in cmd_str and "rev-parse" in cmd_str:
                    res.stdout = "deadbeef\n"
            return res

        mocks["drun"].side_effect = drun_side_effect

    def _run_orchestrator_and_get_dpopen_calls(self, workdir, thinking_value,
                                                setup_mocks_fn=None,
                                                job_dir_base_name="PR_001_test"):
        """Run orchestrator in a temp workdir and return dpopen call list."""
        import orchestrator

        patches = {
            "dbg": patch("orchestrator.dlog", return_value=None),
            "sanity": patch("orchestrator.SanityContext.perform_healthy_check"),
            "teardown": patch("orchestrator.teardown_coder_session"),
            "drun": patch("orchestrator.drun"),
            "dpopen": patch("orchestrator.dpopen"),
            "git_boundary": patch("git_utils.check_git_boundary", MagicMock()),
            "validate_prd": patch("orchestrator.validate_prd_is_committed"),
            "parse_projects": patch("orchestrator.parse_affected_projects", return_value=[]),
            "safe_checkout": patch("orchestrator.safe_git_checkout"),
            "notify": patch("orchestrator.notify_channel"),
            "glob": patch("orchestrator.glob.glob"),
            "pr_depth": patch("orchestrator.get_pr_slice_depth", return_value=0),
            "set_pr_status": patch("orchestrator.set_pr_status"),
            "extract_json": patch("orchestrator.extract_and_parse_json"),
            "get_env": patch("orchestrator.get_env_with_gemini_key", return_value=os.environ.copy()),
            "classify_null": patch("orchestrator.classify_coder_null_output"),
            "head_hash": patch("orchestrator.get_head_commit_hash", return_value="deadbeef"),
            "mainline": patch("orchestrator.get_mainline_branch", return_value="main"),
            "subprocess_run": patch("orchestrator.subprocess.run"),
            "ignition": patch("agent_driver.send_ignition_handshake"),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()

        # Default subprocess.run mock for ensure_run_anchors git calls
        def _default_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.stdout = ""
            res.returncode = 0
            if isinstance(cmd, list) and "rev-parse" in str(cmd):
                res.stdout = "deadbeef\n"
            return res
        mocks["subprocess_run"].side_effect = _default_subprocess_run

        try:
            os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
            global_dir = workdir
            job_dir = self._get_job_dir(workdir, global_dir)
            if setup_mocks_fn:
                setup_mocks_fn(mocks, job_dir, job_dir_base_name)
            else:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mocks["dpopen"].return_value = mock_proc

                def dummy_drun(cmd, *args, **kwargs):
                    res = MagicMock()
                    res.stdout = ""
                    res.returncode = 0
                    if isinstance(cmd, list):
                        if "branch" in str(cmd):
                            res.stdout = "main\n"
                        if "git" in str(cmd) and "rev-parse" in str(cmd):
                            res.stdout = "deadbeef\n"
                    return res
                mocks["drun"].side_effect = dummy_drun

                mocks["classify_null"].return_value = (False, "", "deadbeef")
                mocks["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

            # Set env vars to relax checks for test mode
            with patch.dict(os.environ, {
                "SDLC_TEST_MODE": "true",
                "SDLC_BYPASS_BRANCH_CHECK": "1",
            }):
                argv = self._build_base_argv(workdir, global_dir, thinking=thinking_value)
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            dpopen_calls = list(mocks["dpopen"].call_args_list)
            return dpopen_calls
        finally:
            for p in patches.values():
                p.stop()

    # ------------------------------------------------------------------
    # Test Case 1: reviewer receives default 'high'
    # ------------------------------------------------------------------
    def test_reviewer_spawn_includes_thinking_high_by_default(self):
        """Run orchestrator without --thinking; verify spawn_reviewer dpopen cmd
        contains '--thinking', 'high'."""
        with tempfile.TemporaryDirectory() as workdir:
            dpopen_calls = self._run_orchestrator_and_get_dpopen_calls(
                workdir, None, setup_mocks_fn=self._setup_full_pipeline_mocks)

            reviewer_calls = [
                c for c in dpopen_calls
                if isinstance(c[0][0], list) and "spawn_reviewer.py" in str(c[0][0])
            ]
            self.assertTrue(len(reviewer_calls) > 0,
                            "No spawn_reviewer dpopen call captured")
            cmd = reviewer_calls[0][0][0]
            self.assertIn("--thinking", cmd,
                          f"spawn_reviewer command missing --thinking: {cmd}")
            think_idx = cmd.index("--thinking")
            self.assertEqual(cmd[think_idx + 1], "high",
                             f"Expected thinking='high', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

    # ------------------------------------------------------------------
    # Test Case 2: reviewer receives explicit 'medium'
    # ------------------------------------------------------------------
    def test_reviewer_spawn_includes_thinking_explicit(self):
        """Run orchestrator with --thinking medium; verify spawn_reviewer cmd
        contains '--thinking', 'medium'."""
        with tempfile.TemporaryDirectory() as workdir:
            dpopen_calls = self._run_orchestrator_and_get_dpopen_calls(
                workdir, "medium", setup_mocks_fn=self._setup_full_pipeline_mocks)

            reviewer_calls = [
                c for c in dpopen_calls
                if isinstance(c[0][0], list) and "spawn_reviewer.py" in str(c[0][0])
            ]
            self.assertTrue(len(reviewer_calls) > 0,
                            "No spawn_reviewer dpopen call captured")
            cmd = reviewer_calls[0][0][0]
            self.assertIn("--thinking", cmd)
            think_idx = cmd.index("--thinking")
            self.assertEqual(cmd[think_idx + 1], "medium",
                             f"Expected thinking='medium', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

    # ------------------------------------------------------------------
    # Test Case 3: reviewer retry path is NOT modified
    # ------------------------------------------------------------------
    def test_reviewer_retry_not_modified(self):
        """Verify that the reviewer retry path (with --system-alert) does NOT
        contain --thinking.  Retry thinking wiring is owned by PR-003_1_3."""
        with tempfile.TemporaryDirectory() as workdir:
            dpopen_calls = self._run_orchestrator_and_get_dpopen_calls(
                workdir, "high", setup_mocks_fn=self._setup_full_pipeline_mocks)

            reviewer_calls = [
                c for c in dpopen_calls
                if isinstance(c[0][0], list) and "spawn_reviewer.py" in str(c[0][0])
            ]
            self.assertTrue(len(reviewer_calls) > 0,
                            "No spawn_reviewer dpopen call captured")

            # Filter for retry calls (those with --system-alert)
            retry_calls = [
                c for c in reviewer_calls
                if "--system-alert" in c[0][0]
            ]
            for call in retry_calls:
                cmd = call[0][0]
                self.assertNotIn("--thinking", cmd,
                                 f"Reviewer retry path must not contain --thinking yet (PR-003_1_3). Full cmd: {cmd}")


if __name__ == "__main__":
    unittest.main()
