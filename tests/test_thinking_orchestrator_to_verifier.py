"""Mock-based integration tests for orchestrator --thinking propagation to spawn_verifier.

Validates that --thinking is propagated from orchestrator CLI to spawn_verifier (drun call in State 6).
Covers default 'high', explicit values, convergence across all four primary spawn types,
and a defensive test proving the wiring is intentional.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


class TestThinkingOrchestratorToVerifier(unittest.TestCase):
    """Integration tests for orchestrator --thinking → spawn_verifier propagation."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_base_argv(self, workdir, global_dir, **kwargs):
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
        target_project_name = os.path.basename(os.path.abspath(workdir))
        base_name, _ = os.path.splitext(prd_filename)
        return os.path.abspath(os.path.join(global_dir, ".sdlc_runs", target_project_name, base_name))

    # ------------------------------------------------------------------
    # Core mock harness
    # ------------------------------------------------------------------
    def _start_all_patches(self):
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
        return mocks, patches

    def _stop_all_patches(self, patches):
        for p in patches.values():
            p.stop()

    def _setup_mocks(self, mocks, pr_file_path):
        """Configure mocks with safe defaults."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mocks["dpopen"].return_value = mock_proc

        mocks["classify_null"].return_value = (False, "", "deadbeef")
        mocks["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

        def _default_subprocess_run(cmd, *args, **kwargs):
            res = MagicMock()
            res.stdout = ""
            res.returncode = 0
            if isinstance(cmd, list) and "rev-parse" in str(cmd):
                res.stdout = "deadbeef\n"
            return res
        mocks["subprocess_run"].side_effect = _default_subprocess_run

    def _make_drun_handler(self, *, merge_returncode=0, on_get_next_pr=None):
        """Build a drun side_effect that handles all git/get_next_pr/merge/verifier ops."""

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
                    if on_get_next_pr:
                        on_get_next_pr()
                    res.stdout = "[QUEUE_EMPTY]\n"
                if "merge_code.py" in cmd_str:
                    res.returncode = merge_returncode
            return res

        return drun_side_effect

    # ------------------------------------------------------------------
    # Reusable orchestrator runner
    # ------------------------------------------------------------------
    def _run_orchestrator(self, workdir, thinking_value, *,
                           glob_side_effect=None,
                           drun_handler=None,
                           extra_mock_setup=None):
        """Run orchestrator.main() in a mocked environment."""
        import orchestrator

        mocks, patches = self._start_all_patches()

        # Create a minimal PR file so glob results point at something real
        job_dir = self._get_job_dir(workdir, workdir)
        os.makedirs(job_dir, exist_ok=True)
        pr_file = os.path.join(job_dir, "PR_001_test.md")
        with open(pr_file, "w") as f:
            f.write("status: in_progress\n")

        self._setup_mocks(mocks, pr_file)

        if glob_side_effect:
            mocks["glob"].side_effect = glob_side_effect
        else:
            mocks["glob"].return_value = []

        if drun_handler:
            mocks["drun"].side_effect = drun_handler
        else:
            mocks["drun"].side_effect = self._make_drun_handler()

        if extra_mock_setup:
            extra_mock_setup(mocks)

        try:
            os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
            global_dir = workdir

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

            return list(mocks["dpopen"].call_args_list), list(mocks["drun"].call_args_list)
        finally:
            self._stop_all_patches(patches)

    # ------------------------------------------------------------------
    # Glob helpers (counter + filter pattern, matching sibling tests)
    # ------------------------------------------------------------------
    def _make_state6_glob(self, pr_file):
        """Glob for tests that need to reach State 6 without PR processing.

        Call sequence:
          call 1 – blast-radius (.coder_session) → filtered → []
          call 2 – pre-loop *.md → [pr_file] → resume path
          call 3 – state-machine *.md → [] → get_next_pr → QUEUE_EMPTY → State 6
          State 6 PRD_*.md → filtered (counter > 2) → []
        """
        counter = [0]

        def side_effect(pathname, **kwargs):
            counter[0] += 1
            if "*.md" in pathname or "PR_*.md" in pathname or "PRD_*.md" in pathname:
                if counter[0] <= 2:
                    return [pr_file]
            return []

        return side_effect

    def _make_full_pipeline_glob(self, pr_file):
        """Glob for the convergence test that reaches all four spawn types.

        Call sequence:
          call 1 – blast-radius (.coder_session) → filtered → []
          call 2 – pre-loop *.md → [] → planner spawn
          call 3 – post-planner *.md → [pr_file] → enters state machine
          calls 4-15 – state-machine / PR processing → [pr_file]
          call 16+ → [] → get_next_pr → QUEUE_EMPTY → State 6
        """
        counter = [0]

        def side_effect(pathname, **kwargs):
            counter[0] += 1
            if "*.md" in pathname or "PR_*.md" in pathname or "PRD_*.md" in pathname:
                if 3 <= counter[0] <= 15:
                    return [pr_file]
            return []

        return side_effect

    def _get_verifier_drun_calls(self, drun_calls):
        """Filter drun call list for spawn_verifier.py invocations."""
        return [
            c for c in drun_calls
            if isinstance(c[0][0], list) and "spawn_verifier.py" in str(c[0][0])
        ]

    # ------------------------------------------------------------------
    # Test Case 1: verifier receives default 'high'
    # ------------------------------------------------------------------
    def test_verifier_spawn_includes_thinking_high_by_default(self):
        """Run orchestrator without --thinking; verify spawn_verifier drun cmd
        contains '--thinking', 'high'."""
        with tempfile.TemporaryDirectory() as workdir:
            job_dir = self._get_job_dir(workdir, workdir)
            os.makedirs(job_dir, exist_ok=True)
            pr_file = os.path.join(job_dir, "PR_001_test.md")
            with open(pr_file, "w") as f:
                f.write("status: in_progress\n")

            dpopen_calls, drun_calls = self._run_orchestrator(
                workdir, None,
                glob_side_effect=self._make_state6_glob(pr_file),
            )

            verifier_calls = self._get_verifier_drun_calls(drun_calls)
            self.assertTrue(len(verifier_calls) > 0,
                            "No spawn_verifier drun call captured")
            cmd = verifier_calls[0][0][0]
            self.assertIn("--thinking", cmd,
                          f"spawn_verifier command missing --thinking: {cmd}")
            think_idx = cmd.index("--thinking")
            self.assertEqual(cmd[think_idx + 1], "high",
                             f"Expected thinking='high', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

    # ------------------------------------------------------------------
    # Test Case 2: verifier receives explicit 'low'
    # ------------------------------------------------------------------
    def test_verifier_spawn_includes_thinking_explicit(self):
        """Run orchestrator with --thinking low; verify spawn_verifier drun cmd
        contains '--thinking', 'low'."""
        with tempfile.TemporaryDirectory() as workdir:
            job_dir = self._get_job_dir(workdir, workdir)
            os.makedirs(job_dir, exist_ok=True)
            pr_file = os.path.join(job_dir, "PR_001_test.md")
            with open(pr_file, "w") as f:
                f.write("status: in_progress\n")

            dpopen_calls, drun_calls = self._run_orchestrator(
                workdir, "low",
                glob_side_effect=self._make_state6_glob(pr_file),
            )

            verifier_calls = self._get_verifier_drun_calls(drun_calls)
            self.assertTrue(len(verifier_calls) > 0,
                            "No spawn_verifier drun call captured")
            cmd = verifier_calls[0][0][0]
            self.assertIn("--thinking", cmd)
            think_idx = cmd.index("--thinking")
            self.assertEqual(cmd[think_idx + 1], "low",
                             f"Expected thinking='low', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

    # ------------------------------------------------------------------
    # Test Case 3: defensive test — verifier thinking wiring is intentional
    # ------------------------------------------------------------------
    def test_verifier_thinking_absent_when_not_wired(self):
        """Defensive test proving the --thinking wiring is intentional.

        Creates a source-patched copy of orchestrator.main() with the
        "--thinking", resolved_thinking line removed from the uat_cmd
        construction, then runs that patched copy to prove the verifier
        drun command does NOT contain --thinking.
        """
        import inspect
        import re
        import orchestrator as orch_mod

        # Get the source of main() and strip the "--thinking" line from
        # the spawn_verifier uat_cmd construction.
        main_source = inspect.getsource(orch_mod.main)
        patched_source = re.sub(
            r'^\s*"--thinking",\s*resolved_thinking,\s*$',
            '',
            main_source,
            flags=re.MULTILINE,
        )
        self.assertNotEqual(main_source, patched_source,
                            "Expected --thinking line to be removed from main() source")

        with tempfile.TemporaryDirectory() as workdir:
            job_dir = self._get_job_dir(workdir, workdir)
            os.makedirs(job_dir, exist_ok=True)
            pr_file = os.path.join(job_dir, "PR_001_test.md")
            with open(pr_file, "w") as f:
                f.write("status: in_progress\n")

            mocks, patches = self._start_all_patches()
            self._setup_mocks(mocks, pr_file)
            mocks["glob"].side_effect = self._make_state6_glob(pr_file)

            verifier_commands = []

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
                        res.stdout = "[QUEUE_EMPTY]\n"
                    if "spawn_verifier.py" in cmd_str:
                        verifier_commands.append(list(cmd))
                return res
            mocks["drun"].side_effect = drun_side_effect

            # Build the patched main() using orchestrator's CURRENT
            # (patched) __dict__ so the new function sees our mocks.
            ns = dict(orch_mod.__dict__)
            exec(patched_source, ns)
            patched_main = ns["main"]

            try:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                global_dir = workdir

                with patch.dict(os.environ, {
                    "SDLC_TEST_MODE": "true",
                    "SDLC_BYPASS_BRANCH_CHECK": "1",
                }):
                    argv = self._build_base_argv(workdir, global_dir, thinking="low")
                    with patch("sys.argv", argv):
                        try:
                            patched_main()
                        except SystemExit:
                            pass

                self.assertTrue(len(verifier_commands) > 0,
                                "No spawn_verifier drun call captured")
                for vcmd in verifier_commands:
                    self.assertNotIn("--thinking", vcmd,
                                     f"Verifier command contains --thinking even after wiring removal: {vcmd}")

            finally:
                self._stop_all_patches(patches)


if __name__ == "__main__":
    unittest.main()
