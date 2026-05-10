"""Narrow mock-based integration tests for orchestrator --thinking propagation to primary spawn_planner subprocess.

Validates:
- Default thinking="high" surfaces in spawn_planner argv
- Explicit thinking values propagate correctly
- Illegal values are rejected at parse time
- Both primary planner launch paths (force_replan=true and normal/resume) are covered
"""

import glob as stdlib_glob
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

REAL_GLOB = stdlib_glob.glob

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from planner_test_support import seed_planner_success_artifacts


class TestThinkingOrchestratorPrimary(unittest.TestCase):
    """Integration tests for orchestrator --thinking → spawn_planner propagation."""

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

    def _common_mocks(self):
        """Return patches dict and start them, returning (mocks, patches)."""
        patches = {
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
        }
        mocks = {}
        for key, p in patches.items():
            mocks[key] = p.start()
        return mocks, patches

    def _stop_patches(self, patches):
        for p in patches.values():
            p.stop()

    # ------------------------------------------------------------------
    # Test Case 4: illegal thinking value reject (runs first — no env setup needed)
    # ------------------------------------------------------------------
    def test_orchestrator_rejects_illegal_thinking(self):
        """--thinking invalid must cause argparse SystemExit before any spawn."""
        with tempfile.TemporaryDirectory() as workdir:
            argv = self._build_base_argv(workdir, workdir, thinking="invalid")
            with patch("sys.argv", argv):
                with self.assertRaises(SystemExit) as cm:
                    import orchestrator
                    orchestrator.main()
                self.assertNotEqual(cm.exception.code, 0,
                                    f"Expected non-zero exit for illegal thinking, got {cm.exception.code}")

    # ------------------------------------------------------------------
    # Test Cases 1-3: default / explicit / medium thinking propagation
    # These use Site A (job_dir exists, force_replan=false, no md_files)
    # ------------------------------------------------------------------
    def _run_thinking_test(self, thinking_value, expected):
        """Helper: run orchestrator with given --thinking and verify spawn_planner argv."""
        import orchestrator
        mocks, patches = self._common_mocks()

        try:
            # drun: simulate successful git commands
            def dummy_drun(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = "main\n" if isinstance(cmd, list) and "branch" in cmd else ""
                res.returncode = 0
                return res
            mocks["drun"].side_effect = dummy_drun

            # extract_and_parse_json won't be called (we exit before PR processing)
            mocks["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)

                mock_proc = MagicMock()
                mock_proc.returncode = 0

                def dpopen_side_effect(cmd, *args, **kwargs):
                    if isinstance(cmd, list) and "spawn_planner.py" in str(cmd):
                        seed_planner_success_artifacts(workdir, workdir)
                    return mock_proc

                mocks["dpopen"].side_effect = dpopen_side_effect
                mocks["glob"].side_effect = REAL_GLOB
                argv = self._build_base_argv(workdir, workdir, thinking=thinking_value)

                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # Collect all spawn_planner dpopen calls
            planner_calls = [
                c for c in mocks["dpopen"].call_args_list
                if isinstance(c[0][0], list) and "spawn_planner.py" in str(c[0][0])
            ]
            self.assertTrue(len(planner_calls) > 0,
                            f"No spawn_planner dpopen call captured for --thinking {thinking_value}")

            cmd = planner_calls[0][0][0]
            self.assertIn("--thinking", cmd,
                          f"spawn_planner command missing --thinking: {cmd}")
            think_idx = cmd.index("--thinking")
            self.assertEqual(cmd[think_idx + 1], expected,
                             f"Expected thinking='{expected}', got '{cmd[think_idx + 1]}'. Full cmd: {cmd}")

        finally:
            self._stop_patches(patches)

    def test_orchestrator_accepts_thinking_default(self):
        """Omit --thinking; verify spawn_planner receives default 'high'."""
        self._run_thinking_test(None, "high")

    def test_orchestrator_accepts_thinking_explicit(self):
        """--thinking xhigh; verify spawn_planner receives 'xhigh'."""
        self._run_thinking_test("xhigh", "xhigh")

    def test_orchestrator_accepts_thinking_medium(self):
        """--thinking medium; verify spawn_planner receives 'medium'."""
        self._run_thinking_test("medium", "medium")

    # ------------------------------------------------------------------
    # Test Case 5: both planner paths covered
    # ------------------------------------------------------------------
    def test_orchestrator_thinking_in_both_planner_paths(self):
        """Verify both force_replan=true (Site B) and no-job-dir (Site A) paths pass --thinking."""
        import orchestrator

        # --- Path A: job_dir exists, force_replan=false, no md_files → Site A ---
        mocks_a, patches_a = self._common_mocks()
        try:
            def dummy_drun(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = "main\n" if isinstance(cmd, list) and "branch" in cmd else ""
                res.returncode = 0
                return res
            mocks_a["drun"].side_effect = dummy_drun

            mocks_a["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)

                mock_proc = MagicMock()
                mock_proc.returncode = 0

                def dpopen_side_effect(cmd, *args, **kwargs):
                    if isinstance(cmd, list) and "spawn_planner.py" in str(cmd):
                        seed_planner_success_artifacts(workdir, workdir)
                    return mock_proc

                mocks_a["dpopen"].side_effect = dpopen_side_effect
                mocks_a["glob"].side_effect = REAL_GLOB
                argv = self._build_base_argv(workdir, workdir, thinking=None)
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            path_a_calls = [
                c for c in mocks_a["dpopen"].call_args_list
                if isinstance(c[0][0], list) and "spawn_planner.py" in str(c[0][0])
            ]
            self.assertTrue(len(path_a_calls) > 0,
                            "Path A (force_replan=false, no md_files): expected at least one spawn_planner call")

            for call_args in path_a_calls:
                cmd = call_args[0][0]
                self.assertIn("--thinking", cmd)
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Path A expected thinking='high', got '{cmd[think_idx + 1]}'")
        finally:
            self._stop_patches(patches_a)

        # --- Path B: force_replan=true → outer else block (Site B) ---
        mocks_b, patches_b = self._common_mocks()
        try:
            def dummy_drun(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = "main\n" if isinstance(cmd, list) and "branch" in cmd else ""
                res.returncode = 0
                return res
            mocks_b["drun"].side_effect = dummy_drun

            mocks_b["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

            # Need to mock rmtree because force_replan=true tries to delete job_dir
            mocks_b["rmtree"] = patch("shutil.rmtree").start()

            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)

                mock_proc = MagicMock()
                mock_proc.returncode = 0

                def dpopen_side_effect(cmd, *args, **kwargs):
                    if isinstance(cmd, list) and "spawn_planner.py" in str(cmd):
                        seed_planner_success_artifacts(workdir, workdir)
                    return mock_proc

                mocks_b["dpopen"].side_effect = dpopen_side_effect
                mocks_b["glob"].side_effect = REAL_GLOB
                argv = self._build_base_argv(workdir, workdir, thinking=None, force_replan="true")
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            path_b_calls = [
                c for c in mocks_b["dpopen"].call_args_list
                if isinstance(c[0][0], list) and "spawn_planner.py" in str(c[0][0])
            ]
            self.assertTrue(len(path_b_calls) > 0,
                            "Path B (force_replan=true): expected at least one spawn_planner call")

            for call_args in path_b_calls:
                cmd = call_args[0][0]
                self.assertIn("--thinking", cmd)
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Path B expected thinking='high', got '{cmd[think_idx + 1]}'")
        finally:
            self._stop_patches(patches_b)
            patch.stopall()  # Clean up rmtree patch


if __name__ == "__main__":
    unittest.main()
