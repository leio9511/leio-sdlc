"""Mock-based integration test validating that all four primary-flow spawn types
(planner, coder, reviewer initial, verifier) receive the identical resolved thinking
value from a single orchestrator invocation.

This is a convergence-gate test (PR-003_1_2_3_2): it proves the full primary-flow
thinking chain is closed and uniform, without any spawn path silently diverging.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


class TestThinkingOrchestratorConvergence(unittest.TestCase):
    """Convergence-gate: all four primary spawn types receive identical thinking."""

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
        return os.path.abspath(os.path.join(
            global_dir, ".sdlc_runs", target_project_name, base_name))

    @staticmethod
    def _extract_thinking_value(cmd):
        """Extract the value following '--thinking' from a spawn command list.

        Returns None if --thinking is absent or has no following token.
        """
        try:
            idx = cmd.index("--thinking")
            return cmd[idx + 1]
        except (ValueError, IndexError):
            return None

    # ------------------------------------------------------------------
    # Mock infrastructure
    # ------------------------------------------------------------------
    def _start_all_patches(self):
        """Start all required patches and return (mocks, patches_dict)."""
        patches = {
            "sanity": patch("orchestrator.SanityContext.perform_healthy_check"),
            "teardown": patch("orchestrator.teardown_coder_session"),
            "drun": patch("orchestrator.drun"),
            "dpopen": patch("orchestrator.dpopen"),
            "git_boundary": patch("git_utils.check_git_boundary", MagicMock()),
            "validate_prd": patch("orchestrator.validate_prd_is_committed"),
            "parse_projects": patch(
                "orchestrator.parse_affected_projects", return_value=[]),
            "safe_checkout": patch("orchestrator.safe_git_checkout"),
            "notify": patch("orchestrator.notify_channel"),
            "glob": patch("orchestrator.glob.glob"),
            "pr_depth": patch("orchestrator.get_pr_slice_depth", return_value=0),
            "set_pr_status": patch("orchestrator.set_pr_status"),
            "extract_json": patch("orchestrator.extract_and_parse_json"),
            "get_env": patch(
                "orchestrator.get_env_with_gemini_key",
                return_value=os.environ.copy()),
            "classify_null": patch("orchestrator.classify_coder_null_output"),
            "head_hash": patch(
                "orchestrator.get_head_commit_hash", return_value="deadbeef"),
            "mainline": patch(
                "orchestrator.get_mainline_branch", return_value="main"),
            "subprocess_run": patch("orchestrator.subprocess.run"),
            "ignition": patch("agent_driver.send_ignition_handshake"),
            "dbg": patch("orchestrator.dlog", return_value=None),
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()
        return mocks, patches

    def _stop_all_patches(self, patches):
        """Stop all patches started by _start_all_patches."""
        for p in patches.values():
            p.stop()

    def _configure_default_mocks(self, mocks):
        """Apply default return-value mocks that all convergence tests need."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mocks["dpopen"].return_value = mock_proc

        mocks["classify_null"].return_value = (False, "", "deadbeef")
        mocks["extract_json"].return_value = {
            "overall_assessment": "EXCELLENT"}

        def _default_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.stdout = ""
            res.returncode = 0
            if isinstance(cmd, list) and "rev-parse" in str(cmd):
                res.stdout = "deadbeef\n"
            return res
        mocks["subprocess_run"].side_effect = _default_subprocess_run

    def _make_drun_handler(self, *, uat_file=None, get_next_pr_returns=None):
        """Build a drun side_effect covering git, get_next_pr, merge, verifier.

        uat_file: if provided, write {"status":"PASS"} to this path when the
                  spawn_verifier drun call fires, so the UAT retry loop
                  succeeds on the first pass.
        get_next_pr_returns: list of stdout strings consumed in call order;
                             None entries are skipped and yield empty stdout.
        """
        next_pr_idx = [0]

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
                if "get_next_pr" in cmd_str:
                    if get_next_pr_returns:
                        idx = next_pr_idx[0]
                        next_pr_idx[0] = idx + 1
                        if idx < len(get_next_pr_returns):
                            stdout = get_next_pr_returns[idx]
                            if stdout is not None:
                                res.stdout = stdout
                    else:
                        res.stdout = "[QUEUE_EMPTY]\n"
                if "merge_code.py" in cmd_str:
                    res.returncode = 0
                if "spawn_verifier.py" in cmd_str and uat_file:
                    import json as _json
                    os.makedirs(os.path.dirname(uat_file), exist_ok=True)
                    with open(uat_file, "w") as f:
                        _json.dump(
                            {"status": "PASS", "verification_details": []}, f)
            return res

        return drun_side_effect

    # ------------------------------------------------------------------
    # Convergence runner (single test-exercise of all four spawn paths)
    # ------------------------------------------------------------------
    def _run_convergence(self, thinking_value):
        """Run orchestrator through the full primary-flow pipeline and return
        a dict mapping each spawn type to its captured thinking value.

        Returns:
            {
                "planner":  thinking_value | None,
                "coder":    thinking_value | None,
                "reviewer": thinking_value | None,
                "verifier": thinking_value | None,
            }
        """
        import orchestrator

        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        try:
            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                global_dir = workdir
                job_dir = self._get_job_dir(workdir, global_dir)
                os.makedirs(job_dir, exist_ok=True)

                # PR file with status 'in_progress' so the state-machine resumes it
                pr_file = os.path.join(job_dir, "PR_001_test.md")
                with open(pr_file, "w") as f:
                    f.write("status: in_progress\n")

                # Path for the uat_report.json the verifier will try to read
                run_dir = os.path.join(job_dir, "run")
                os.makedirs(run_dir, exist_ok=True)
                uat_file = os.path.abspath(
                    os.path.join(run_dir, "uat_report.json"))

                # Glob call sequence (counter-based so the pipeline advances):
                #   call 1 – blast-radius .coder_session → no match → []
                #   call 2 – resume-path check (line ~728) → [] → planner runs
                #   call 3 – post-planner checks (line ~757) → [pr_file] → proceed
                #   call 4 – state-machine 1st iteration → [pr_file] → process PR
                #   call 5 – state-machine 2nd iteration → [] → get_next_pr → verifier
                glob_counter = [0]

                def glob_side_effect(pathname, **kwargs):
                    glob_counter[0] += 1
                    c = glob_counter[0]
                    if ("*.md" in pathname or "PR_*.md" in pathname
                            or "PRD_*.md" in pathname):
                        if c in (3, 4):
                            return [pr_file]
                    return []

                mocks["glob"].side_effect = glob_side_effect

                # drun: git commands succeed, get_next_pr returns QUEUE_EMPTY
                # on the second call (after the one PR is done), and verifier
                # writes a passing uat_report.json.
                mocks["drun"].side_effect = self._make_drun_handler(
                    uat_file=uat_file,
                    get_next_pr_returns=[None, "[QUEUE_EMPTY]\n"],
                )

                with patch.dict(os.environ, {
                    "SDLC_TEST_MODE": "true",
                    "SDLC_BYPASS_BRANCH_CHECK": "1",
                }):
                    argv = self._build_base_argv(
                        workdir, global_dir, thinking=thinking_value)
                    with patch("sys.argv", argv):
                        try:
                            orchestrator.main()
                        except SystemExit:
                            pass

                # ---- Collect all spawn commands from both dpopen and drun ----
                dpopen_calls = list(mocks["dpopen"].call_args_list)
                drun_calls = list(mocks["drun"].call_args_list)

                results = {
                    "planner":  None,
                    "coder":    None,
                    "reviewer": None,
                    "verifier": None,
                }

                # dpopen hosts planner, coder, and reviewer (initial)
                for call in dpopen_calls:
                    cmd = call[0][0]
                    if not isinstance(cmd, list):
                        continue
                    cmd_str = str(cmd)
                    if "spawn_planner.py" in cmd_str and "--thinking" in cmd:
                        results["planner"] = self._extract_thinking_value(cmd)
                    elif "spawn_coder.py" in cmd_str and "--thinking" in cmd:
                        results["coder"] = self._extract_thinking_value(cmd)
                    elif ("spawn_reviewer.py" in cmd_str
                          and "--thinking" in cmd):
                        # Exclude retry calls (they carry --system-alert)
                        if "--system-alert" not in cmd:
                            results["reviewer"] = (
                                self._extract_thinking_value(cmd))

                # drun hosts verifier
                for call in drun_calls:
                    cmd = call[0][0]
                    if not isinstance(cmd, list):
                        continue
                    cmd_str = str(cmd)
                    if "spawn_verifier.py" in cmd_str and "--thinking" in cmd:
                        results["verifier"] = self._extract_thinking_value(cmd)

                return results

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 1 – explicit --thinking xhigh → uniform propagation
    # ------------------------------------------------------------------
    def test_all_four_primary_spawn_types_receive_same_thinking(self):
        """Run orchestrator with --thinking xhigh; verify that spawn_planner,
        spawn_coder, spawn_reviewer (initial), and spawn_verifier command lists
        ALL contain '--thinking', 'xhigh', and that all four extract the
        identical thinking value.
        """
        results = self._run_convergence("xhigh")

        self.assertIsNotNone(
            results["planner"],
            "No spawn_planner call captured")
        self.assertIsNotNone(
            results["coder"],
            "No spawn_coder call captured")
        self.assertIsNotNone(
            results["reviewer"],
            "No spawn_reviewer (initial) call captured")
        self.assertIsNotNone(
            results["verifier"],
            "No spawn_verifier call captured")

        self.assertEqual(results["planner"], "xhigh",
                         f"Planner thinking mismatch: {results['planner']}")
        self.assertEqual(results["coder"], "xhigh",
                         f"Coder thinking mismatch: {results['coder']}")
        self.assertEqual(results["reviewer"], "xhigh",
                         f"Reviewer thinking mismatch: {results['reviewer']}")
        self.assertEqual(results["verifier"], "xhigh",
                         f"Verifier thinking mismatch: {results['verifier']}")

        # Bonus assertion: every spawn type got the exact same value
        unique_values = set(results.values())
        self.assertEqual(
            len(unique_values), 1,
            f"Expected all four spawn types to receive the identical "
            f"thinking value, got: {results}")

    # ------------------------------------------------------------------
    # Test Case 2 – omitted --thinking → default 'high' for all
    # ------------------------------------------------------------------
    def test_convergence_holds_with_default_thinking(self):
        """Run orchestrator without --thinking; verify that all four primary
        spawn command lists contain '--thinking', 'high' (the default), and
        that no spawn type received a different thinking value.
        """
        results = self._run_convergence(None)

        self.assertIsNotNone(
            results["planner"],
            "No spawn_planner call captured")
        self.assertIsNotNone(
            results["coder"],
            "No spawn_coder call captured")
        self.assertIsNotNone(
            results["reviewer"],
            "No spawn_reviewer (initial) call captured")
        self.assertIsNotNone(
            results["verifier"],
            "No spawn_verifier call captured")

        self.assertEqual(results["planner"], "high",
                         f"Planner thinking mismatch: {results['planner']}")
        self.assertEqual(results["coder"], "high",
                         f"Coder thinking mismatch: {results['coder']}")
        self.assertEqual(results["reviewer"], "high",
                         f"Reviewer thinking mismatch: {results['reviewer']}")
        self.assertEqual(results["verifier"], "high",
                         f"Verifier thinking mismatch: {results['verifier']}")

        unique_values = set(results.values())
        self.assertEqual(
            len(unique_values), 1,
            f"Expected all four spawn types to receive the identical "
            f"default thinking value 'high', got: {results}")


if __name__ == "__main__":
    unittest.main()
