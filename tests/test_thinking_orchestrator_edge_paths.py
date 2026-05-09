"""Mock-based integration tests for orchestrator --thinking propagation
through non-primary (edge-case) spawn paths: UAT recovery replan,
reviewer retry with system alert, and state 5 re-slice.

Validates that the resolved thinking value persists through all three
recovery/retry codepaths in addition to the primary paths.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


class TestThinkingOrchestratorEdgePaths(unittest.TestCase):
    """Integration tests for orchestrator --thinking propagation to edge-case spawn paths."""

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
        """Extract the value following '--thinking' from a spawn command list."""
        try:
            idx = cmd.index("--thinking")
            return cmd[idx + 1]
        except (ValueError, IndexError):
            return None

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
        """Apply default return-value mocks that all tests need."""
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

    def _make_basic_drun_handler(self, *, uat_file=None, uat_status="PASS",
                                  get_next_pr_returns=None):
        """Build a drun side_effect covering git, get_next_pr, merge, verifier."""
        next_pr_idx = [0]

        def _side_effect(cmd, *args, **kwargs):
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
                    content = {"status": uat_status, "verification_details": []}
                    if uat_status == "NEEDS_FIX":
                        content["verification_details"] = [
                            {"status": "MISSING", "description": "Test item"}
                        ]
                    with open(uat_file, "w") as f:
                        _json.dump(content, f)
            return res

        return _side_effect

    def _glob_return_pr_on_calls(self, pr_file, calls):
        """Return a glob side_effect that returns [pr_file] on specific call indices."""
        glob_counter = [0]

        def glob_side_effect(pathname, **kwargs):
            glob_counter[0] += 1
            c = glob_counter[0]
            if ("*.md" in pathname or "PR_*.md" in pathname
                    or "PRD_*.md" in pathname):
                if c in calls:
                    return [pr_file]
            return []

        return glob_side_effect

    def _setup_and_run(self, mocks, workdir, thinking_value, *,
                        job_dir_base_name="PR_001_test",
                        drun_kwargs=None,
                        glob_calls_for_pr=None,
                        extra_mock_setup=None):
        """Common setup + orchestrator run for all edge-path tests."""
        import orchestrator

        os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
        global_dir = workdir
        job_dir = self._get_job_dir(workdir, global_dir)
        os.makedirs(job_dir, exist_ok=True)

        pr_file = os.path.join(job_dir, f"{job_dir_base_name}.md")
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")

        # UAT report path for verifier drun handler
        # orchestrator sets run_dir = job_dir (line 681)
        uat_file = os.path.abspath(os.path.join(job_dir, "uat_report.json"))

        # Glob
        glob_calls = glob_calls_for_pr or {3, 4}
        mocks["glob"].side_effect = self._glob_return_pr_on_calls(pr_file, glob_calls)

        # Drun
        drun_opts = drun_kwargs or {}
        mocks["drun"].side_effect = self._make_basic_drun_handler(
            uat_file=uat_file, **drun_opts)

        if extra_mock_setup:
            extra_mock_setup(mocks)

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
        drun_calls = list(mocks["drun"].call_args_list)
        return dpopen_calls, drun_calls

    # ------------------------------------------------------------------
    # Test Case 1: UAT recovery replan includes explicit thinking
    # ------------------------------------------------------------------
    def test_uat_recovery_replan_includes_thinking(self):
        """Run orchestrator with --thinking medium; trigger UAT recovery path.
        Verify UAT recovery spawn_planner dpopen cmd contains '--thinking', 'medium'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, "medium",
                    drun_kwargs={
                        "uat_status": "NEEDS_FIX",
                        "get_next_pr_returns": ["[QUEUE_EMPTY]\n"],
                    },
                )

                uat_replan_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_planner.py" in str(c[0][0])
                    and "--replan-uat-failures" in c[0][0]
                ]
                self.assertTrue(len(uat_replan_calls) > 0,
                                "No UAT recovery spawn_planner dpopen call captured")
                cmd = uat_replan_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"UAT recovery command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "medium",
                                 f"Expected thinking='medium', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 2: UAT recovery replan includes default thinking
    # ------------------------------------------------------------------
    def test_uat_recovery_replan_includes_thinking_default(self):
        """Run orchestrator without --thinking; trigger UAT recovery path.
        Verify UAT recovery spawn_planner dpopen cmd contains '--thinking', 'high'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, None,
                    drun_kwargs={
                        "uat_status": "NEEDS_FIX",
                        "get_next_pr_returns": ["[QUEUE_EMPTY]\n"],
                    },
                )

                uat_replan_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_planner.py" in str(c[0][0])
                    and "--replan-uat-failures" in c[0][0]
                ]
                self.assertTrue(len(uat_replan_calls) > 0,
                                "No UAT recovery spawn_planner dpopen call captured")
                cmd = uat_replan_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"UAT recovery command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Expected thinking='high', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 3: Reviewer retry with system alert includes explicit thinking
    # ------------------------------------------------------------------
    def test_reviewer_retry_with_system_alert_includes_thinking(self):
        """Run orchestrator with --thinking xhigh; mock reviewer parse failure
        to trigger JSON retry with --system-alert. Verify the retry dpopen
        command contains '--thinking', 'xhigh'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        # extract_and_parse_json: raise ValueError first time → retry,
        # succeed second time
        extract_call_count = [0]

        def extract_json_side_effect(content):
            extract_call_count[0] += 1
            if extract_call_count[0] == 1:
                raise ValueError("Simulated parse failure")
            return {"overall_assessment": "EXCELLENT"}

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, "xhigh",
                    drun_kwargs={
                        "get_next_pr_returns": ["PR_001_test\n", "[QUEUE_EMPTY]\n"],
                    },
                    extra_mock_setup=lambda m: setattr(
                        m["extract_json"], "side_effect", extract_json_side_effect),
                )

                retry_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_reviewer.py" in str(c[0][0])
                    and "--system-alert" in c[0][0]
                ]
                self.assertTrue(len(retry_calls) > 0,
                                "No reviewer retry (--system-alert) dpopen call captured")
                cmd = retry_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"Reviewer retry command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "xhigh",
                                 f"Expected thinking='xhigh', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 4: Reviewer retry includes default thinking
    # ------------------------------------------------------------------
    def test_reviewer_retry_includes_thinking_default(self):
        """Run orchestrator without --thinking; trigger reviewer retry.
        Verify reviewer retry dpopen cmd contains '--thinking', 'high'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        extract_call_count = [0]

        def extract_json_side_effect(content):
            extract_call_count[0] += 1
            if extract_call_count[0] == 1:
                raise ValueError("Simulated parse failure")
            return {"overall_assessment": "EXCELLENT"}

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, None,
                    drun_kwargs={
                        "get_next_pr_returns": ["PR_001_test\n", "[QUEUE_EMPTY]\n"],
                    },
                    extra_mock_setup=lambda m: setattr(
                        m["extract_json"], "side_effect", extract_json_side_effect),
                )

                retry_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_reviewer.py" in str(c[0][0])
                    and "--system-alert" in c[0][0]
                ]
                self.assertTrue(len(retry_calls) > 0,
                                "No reviewer retry (--system-alert) dpopen call captured")
                cmd = retry_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"Reviewer retry command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Expected thinking='high', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 5: State 5 re-slice includes explicit thinking
    # ------------------------------------------------------------------
    def test_state5_reslice_includes_thinking(self):
        """Run orchestrator with --thinking low; exhaust coder retries and
        trigger state 5 re-slice. Verify re-slice spawn_planner dpopen cmd
        contains '--thinking', 'low'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        # classify_coder_null_output: always null → retries exhaust → state 5
        # get_pr_slice_depth returns 0 (< 2) → triggers re-slice
        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, "low",
                    drun_kwargs={
                        "get_next_pr_returns": ["PR_001_test\n", "[QUEUE_EMPTY]\n"],
                    },
                    extra_mock_setup=lambda m: (
                        setattr(m["classify_null"], "return_value",
                                (True, "empty_coder_output", "")),
                        setattr(m["pr_depth"], "return_value", 0),
                    ),
                )

                reslice_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_planner.py" in str(c[0][0])
                    and "--slice-failed-pr" in c[0][0]
                ]
                self.assertTrue(len(reslice_calls) > 0,
                                "No state 5 re-slice (--slice-failed-pr) dpopen call captured")
                cmd = reslice_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"State 5 re-slice command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "low",
                                 f"Expected thinking='low', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 6: State 5 re-slice includes default thinking
    # ------------------------------------------------------------------
    def test_state5_reslice_includes_thinking_default(self):
        """Run orchestrator without --thinking; trigger state 5 re-slice.
        Verify re-slice spawn_planner dpopen cmd contains '--thinking', 'high'.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, _ = self._setup_and_run(
                    mocks, workdir, None,
                    drun_kwargs={
                        "get_next_pr_returns": ["PR_001_test\n", "[QUEUE_EMPTY]\n"],
                    },
                    extra_mock_setup=lambda m: (
                        setattr(m["classify_null"], "return_value",
                                (True, "empty_coder_output", "")),
                        setattr(m["pr_depth"], "return_value", 0),
                    ),
                )

                reslice_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and "spawn_planner.py" in str(c[0][0])
                    and "--slice-failed-pr" in c[0][0]
                ]
                self.assertTrue(len(reslice_calls) > 0,
                                "No state 5 re-slice (--slice-failed-pr) dpopen call captured")
                cmd = reslice_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"State 5 re-slice command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Expected thinking='high', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Test Case 7: Exhaustive coverage — all spawn calls receive thinking
    # ------------------------------------------------------------------
    def test_orchestrator_all_spawn_calls_complete_coverage(self):
        """Run orchestrator with --thinking xhigh through a full mock that
        exercises EVERY spawn call site. Verify every captured command list
        contains '--thinking', 'xhigh'. This is the convergence proof for
        the orchestrator layer.
        """
        mocks, patches = self._start_all_patches()
        self._configure_default_mocks(mocks)

        # Trigger reviewer retry so that path is also exercised
        extract_call_count = [0]

        def extract_json_side_effect(content):
            extract_call_count[0] += 1
            if extract_call_count[0] == 1:
                raise ValueError("Simulated parse failure")
            return {"overall_assessment": "EXCELLENT"}

        try:
            with tempfile.TemporaryDirectory() as workdir:
                dpopen_calls, drun_calls = self._setup_and_run(
                    mocks, workdir, "xhigh",
                    drun_kwargs={
                        "get_next_pr_returns": ["PR_001_test\n", "[QUEUE_EMPTY]\n"],
                    },
                    extra_mock_setup=lambda m: setattr(
                        m["extract_json"], "side_effect", extract_json_side_effect),
                )

                # Collect ALL spawn commands from dpopen
                spawn_calls = [
                    c for c in dpopen_calls
                    if isinstance(c[0][0], list)
                    and ("spawn_planner.py" in str(c[0][0])
                         or "spawn_coder.py" in str(c[0][0])
                         or "spawn_reviewer.py" in str(c[0][0])
                         or "spawn_verifier.py" in str(c[0][0]))
                ]

                # Check drun calls for spawn_verifier
                verifier_drun_calls = [
                    c for c in drun_calls
                    if isinstance(c[0][0], list)
                    and "spawn_verifier.py" in str(c[0][0])
                ]

                # Categorize captured spawn types
                spawn_types = []
                for c in spawn_calls:
                    cmd = c[0][0]
                    if "spawn_planner.py" in str(cmd):
                        if "--replan-uat-failures" in cmd:
                            spawn_types.append("planner(UAT-recovery)")
                        elif "--slice-failed-pr" in cmd:
                            spawn_types.append("planner(re-slice)")
                        else:
                            spawn_types.append("planner(primary)")
                    elif "spawn_coder.py" in str(cmd):
                        spawn_types.append("coder")
                    elif "spawn_reviewer.py" in str(cmd):
                        if "--system-alert" in cmd:
                            spawn_types.append("reviewer(retry)")
                        else:
                            spawn_types.append("reviewer(initial)")

                for c in verifier_drun_calls:
                    cmd = c[0][0]
                    if "spawn_verifier.py" in str(cmd):
                        spawn_types.append("verifier")

                print(f"\nCaptured spawn types: {spawn_types}")

                # Verify every spawn dpopen call contains --thinking xhigh
                for call in spawn_calls:
                    cmd = call[0][0]
                    cmd_str = str(cmd)
                    self.assertIn("--thinking", cmd,
                                  f"Spawn command missing --thinking: {cmd_str[:200]}")
                    think_idx = cmd.index("--thinking")
                    self.assertEqual(cmd[think_idx + 1], "xhigh",
                                     f"Expected thinking='xhigh', got '{cmd[think_idx + 1]}'. Cmd: {cmd_str[:200]}")

                # Verify verifier drun calls also contain --thinking
                for call in verifier_drun_calls:
                    cmd = call[0][0]
                    cmd_str = str(cmd)
                    self.assertIn("--thinking", cmd,
                                  f"Verifier drun command missing --thinking: {cmd_str[:200]}")
                    think_idx = cmd.index("--thinking")
                    self.assertEqual(cmd[think_idx + 1], "xhigh",
                                     f"Expected thinking='xhigh', got '{cmd[think_idx + 1]}'. Cmd: {cmd_str[:200]}")

                # Sanity: we exercised multiple spawn types
                self.assertGreaterEqual(len(spawn_types), 4,
                                        f"Expected at least 4 spawn calls across types, got {len(spawn_types)}: {spawn_types}")

        finally:
            self._stop_all_patches(patches)


if __name__ == "__main__":
    unittest.main()
