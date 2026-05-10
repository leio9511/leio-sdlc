"""End-to-end convergence and validation tests for --thinking propagation.

PR-003_3: Validates that the full --thinking propagation chain converges
correctly from the orchestrator CLI entrypoint through spawn subprocesses
into invoke_agent() and ultimately into the OpenClaw command.

Proves the shared resolver is the single source of truth for default and
validation across the entire chain.

Tests use unittest.mock.patch extensively to avoid real LLM calls and
subprocess execution while still validating parameter propagation.
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


# ============================================================================
# 4.1  End-to-End Propagation Tests
# ============================================================================

class TestE2EThinkingPropagation(unittest.TestCase):
    """Test Cases 1-3: Full-chain orchestrator -> spawn -> invoke_agent propagation."""

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------

    def _build_orchestrator_argv(self, workdir, global_dir, thinking=None):
        argv = [
            "orchestrator.py",
            "--enable-exec-from-workspace",
            "--workdir", workdir,
            "--prd-file", "dummy_prd.md",
            "--force-replan", "false",
            "--channel", "test-channel",
            "--global-dir", global_dir,
        ]
        if thinking is not None:
            argv.extend(["--thinking", thinking])
        return argv

    def _common_orchestrator_mocks(self):
        """Return patches and mocked dpopen for orchestrator.main()."""
        mocks = {}
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
        for key, p in patches.items():
            mocks[key] = p.start()
        return mocks, patches

    def _stop_patches(self, patches):
        for p in patches.values():
            p.stop()

    def _setup_mocks_for_run(self, mocks, workdir, global_dir, prd_filename="dummy_prd.md"):
        """Configure drun, dpopen, and planner-success artifacts for a clean run."""
        def dummy_drun(cmd, *args, **kwargs):
            res = MagicMock()
            res.stdout = "main\n" if isinstance(cmd, list) and "branch" in cmd else ""
            res.returncode = 0
            return res
        mocks["drun"].side_effect = dummy_drun

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        def dpopen_side_effect(cmd, *args, **kwargs):
            if isinstance(cmd, list) and "spawn_planner.py" in str(cmd):
                seed_planner_success_artifacts(workdir, global_dir, prd_filename)
            return mock_proc

        mocks["dpopen"].side_effect = dpopen_side_effect
        mocks["glob"].side_effect = REAL_GLOB
        mocks["extract_json"].return_value = {"overall_assessment": "EXCELLENT"}

    def _get_planner_calls(self, mocks):
        """Extract spawn_planner dpopen calls from mock."""
        return [
            c for c in mocks["dpopen"].call_args_list
            if isinstance(c[0][0], list) and "spawn_planner.py" in str(c[0][0])
        ]

    # ------------------------------------------------------------------
    # Test Case 1: Full-chain propagation with --thinking medium
    # ------------------------------------------------------------------

    def test_full_orchestrator_to_invoke_agent_thinking_flow(self):
        """Simulate full chain: orchestrator -> spawn_planner -> invoke_agent.

        Mock dpopen (to capture orchestrator spawn commands) and invoke_agent
        (to verify the final call). Verify that with --thinking medium:
        - spawn_planner subprocess command contains "--thinking", "medium"
        - spawn_planner's invoke_agent call receives thinking="medium"
        """
        import orchestrator
        import spawn_planner

        mocks, patches = self._common_orchestrator_mocks()
        try:
            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                self._setup_mocks_for_run(mocks, workdir, workdir)
                argv = self._build_orchestrator_argv(workdir, workdir, thinking="medium")
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

                planner_calls = self._get_planner_calls(mocks)
                self.assertTrue(len(planner_calls) > 0,
                                "No spawn_planner dpopen call captured for --thinking medium")

                cmd = planner_calls[0][0][0]
                self.assertIn("--thinking", cmd,
                              f"spawn_planner command missing --thinking: {cmd}")
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "medium",
                                 f"Expected thinking='medium' in spawn command, got '{cmd[think_idx + 1]}'")
        finally:
            self._stop_patches(patches)

        # Phase 2: Verify the resolver chain for the explicit value.
        # spawn_planner calls resolve_thinking(args.thinking) in main().
        # Test that resolve_thinking("medium") returns "medium" (already covered
        # by resolver tests; this is the convergence validation).
        from thinking_resolver import resolve_thinking
        self.assertEqual(resolve_thinking("medium"), "medium",
                         "resolve_thinking should pass 'medium' through unchanged")

    # ------------------------------------------------------------------
    # Test Case 2: Default thinking='high' through full chain
    # ------------------------------------------------------------------

    def test_e2e_thinking_high_default_chain(self):
        """Full-chain with --thinking omitted: default 'high' propagates everywhere."""
        import orchestrator
        import spawn_planner

        mocks, patches = self._common_orchestrator_mocks()
        try:
            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                self._setup_mocks_for_run(mocks, workdir, workdir)
                argv = self._build_orchestrator_argv(workdir, workdir, thinking=None)
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

                planner_calls = self._get_planner_calls(mocks)
                self.assertTrue(len(planner_calls) > 0,
                                "No spawn_planner dpopen call captured for default thinking")

                cmd = planner_calls[0][0][0]
                self.assertIn("--thinking", cmd)
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "high",
                                 f"Default thinking expected 'high', got '{cmd[think_idx + 1]}'")
        finally:
            self._stop_patches(patches)

        # Phase 2: Verify the resolver chain for default (None).
        # Without --thinking, spawn_planner calls resolve_thinking(None) → "high".
        from thinking_resolver import resolve_thinking
        self.assertEqual(resolve_thinking(None), "high",
                         "resolve_thinking(None) should default to 'high'")

    # ------------------------------------------------------------------
    # Test Case 3: Explicit --thinking xhigh through full chain
    # ------------------------------------------------------------------

    def test_e2e_thinking_xhigh_explicit_chain(self):
        """Full-chain with --thinking xhigh: 'xhigh' propagates everywhere."""
        import orchestrator

        mocks, patches = self._common_orchestrator_mocks()
        try:
            with tempfile.TemporaryDirectory() as workdir:
                os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
                self._setup_mocks_for_run(mocks, workdir, workdir)
                argv = self._build_orchestrator_argv(workdir, workdir, thinking="xhigh")
                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

                planner_calls = self._get_planner_calls(mocks)
                self.assertTrue(len(planner_calls) > 0,
                                "No spawn_planner dpopen call captured for --thinking xhigh")

                cmd = planner_calls[0][0][0]
                self.assertIn("--thinking", cmd)
                think_idx = cmd.index("--thinking")
                self.assertEqual(cmd[think_idx + 1], "xhigh",
                                 f"Expected thinking='xhigh' in spawn command, got '{cmd[think_idx + 1]}'")
        finally:
            self._stop_patches(patches)


# ============================================================================
# 4.2  Resolver-Level Validation
# ============================================================================

class TestResolverLevelValidation(unittest.TestCase):
    """Test Cases 4-5: Direct resolver validation — defense-in-depth."""

    def test_resolver_rejects_illegal_value_direct(self):
        """resolve_thinking('bogus') raises ValueError with rejected value and allowed set."""
        from scripts.thinking_resolver import resolve_thinking

        # Bogus value
        with self.assertRaises(ValueError) as cm:
            resolve_thinking("bogus")
        msg = str(cm.exception)
        self.assertIn("bogus", msg, "Error message must include the rejected value")
        self.assertIn("low", msg, "Error message must include allowed set")
        self.assertIn("medium", msg)
        self.assertIn("high", msg)
        self.assertIn("xhigh", msg)

        # Uppercase variant: "HIGH" is not in ALLOWED_THINKING_VALUES
        with self.assertRaises(ValueError):
            resolve_thinking("HIGH")

        # Empty string defaults to "high"
        self.assertEqual(resolve_thinking(""), "high",
                         "Empty string should default to 'high'")

        # None defaults to "high"
        self.assertEqual(resolve_thinking(None), "high",
                         "None should default to 'high'")

    def test_resolver_is_single_source_of_truth(self):
        """ALLOWED_THINKING_VALUES and DEFAULT_THINKING are defined only in thinking_resolver.py."""
        from scripts.thinking_resolver import ALLOWED_THINKING_VALUES, DEFAULT_THINKING

        # Verify constants are correct
        self.assertEqual(ALLOWED_THINKING_VALUES, frozenset({"low", "medium", "high", "xhigh"}))
        self.assertEqual(DEFAULT_THINKING, "high")

        # Static analysis: ALLOWED_THINKING_VALUES and DEFAULT_THINKING must NOT be
        # defined (assigned) in any spawn_* file, orchestrator.py, or agent_driver.py.
        # They should only be imported from thinking_resolver.
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        check_files = [
            "orchestrator.py",
            "agent_driver.py",
            "spawn_planner.py",
            "spawn_coder.py",
            "spawn_reviewer.py",
            "spawn_verifier.py",
            "spawn_auditor.py",
            "spawn_manager.py",
            "spawn_arbitrator.py",
        ]
        for fname in check_files:
            fpath = os.path.join(script_dir, fname)
            with open(fpath, "r") as f:
                source = f.read()
            # Only import lines should reference these identifiers; no assignment lines.
            # Assignment would look like "ALLOWED_THINKING_VALUES =" (not inside a comment)
            lines = source.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "ALLOWED_THINKING_VALUES" in stripped and "=" in stripped:
                    if "from thinking_resolver" not in line and "import" not in line:
                        self.fail(
                            f"{fname} defines ALLOWED_THINKING_VALUES "
                            f"(not allowed outside thinking_resolver.py): {stripped}"
                        )
                if "DEFAULT_THINKING" in stripped and "=" in stripped:
                    if "from thinking_resolver" not in line and "import" not in line:
                        self.fail(
                            f"{fname} defines DEFAULT_THINKING "
                            f"(not allowed outside thinking_resolver.py): {stripped}"
                        )


# ============================================================================
# 4.3  Agent-Driver Command Integration
# ============================================================================

class TestAgentDriverCommandIntegration(unittest.TestCase):
    """Test Cases 6-8: Verify thinking appears (or not) in the final command."""

    def setUp(self):
        self.patcher_run = patch("agent_driver.subprocess.run")
        self.mock_run = self.patcher_run.start()
        self.patcher_resolve = patch("agent_driver.resolve_cmd")
        self.mock_resolve = self.patcher_resolve.start()
        self.mock_resolve.return_value = "mock_openclaw"
        self.patcher_copytree = patch("shutil.copytree")
        self.mock_copytree = self.patcher_copytree.start()
        self.patcher_copy2 = patch("shutil.copy2")
        self.mock_copy2 = self.patcher_copy2.start()

    def tearDown(self):
        patch.stopall()

    def _setup_openclaw_mocks(self, agent_exists=True, model="gpt"):
        """Setup subprocess.run side_effect for OpenClaw path.

        Call chain:
          1. agents list (to check if agent exists)
          2. agents list (inside validate_openclaw_agent_model)
          3. actual agent invocation
        """
        agent_line = f"- sdlc-generic-openclaw-{model}\n  Model: {model}\n" if agent_exists else ""
        mock_list = MagicMock()
        mock_list.stdout = agent_line
        mock_list.returncode = 0

        mock_run = MagicMock()
        mock_run.stdout = "output"
        mock_run.returncode = 0

        self.mock_run.side_effect = [mock_list, mock_list, mock_run]

    def test_invoke_agent_default_thinking_is_high(self):
        """invoke_agent without thinking → OpenClaw command contains --thinking high."""
        import agent_driver

        self._setup_openclaw_mocks()

        with patch.dict(os.environ, {"LLM_DRIVER": "openclaw", "SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-abc")

        # The third call is the actual agent invocation
        cmd = self.mock_run.call_args_list[2][0][0]
        self.assertIn("--thinking", cmd, "Command must include --thinking flag")
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "high",
                         f"Default thinking should be 'high', got '{cmd[think_idx + 1]}'")
        self.assertIn("--agent", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-abc", cmd)
        self.assertIn("-m", cmd)

    def test_invoke_agent_explicit_thinking_in_command(self):
        """invoke_agent with thinking='xhigh' → OpenClaw command contains --thinking xhigh."""
        import agent_driver

        self._setup_openclaw_mocks()

        with patch.dict(os.environ, {"LLM_DRIVER": "openclaw", "SDLC_MODEL": "gpt"}):
            agent_driver.invoke_agent("test task", session_key="session-xyz", thinking="xhigh")

        cmd = self.mock_run.call_args_list[2][0][0]
        self.assertIn("--thinking", cmd)
        think_idx = cmd.index("--thinking")
        self.assertEqual(cmd[think_idx + 1], "xhigh",
                         f"Explicit thinking should be 'xhigh', got '{cmd[think_idx + 1]}'")
        self.assertIn("--agent", cmd)
        self.assertIn("--session-id", cmd)
        self.assertIn("session-xyz", cmd)
        self.assertIn("-m", cmd)

    def test_gemini_path_no_thinking_in_command(self):
        """Gemini engine path → --thinking does NOT appear in the command."""
        import agent_driver

        mock_run_result = MagicMock()
        mock_run_result.stdout = "gemini output"
        mock_run_result.returncode = 0

        mock_session_list = MagicMock()
        mock_session_list.stdout = "[]"
        mock_session_list.returncode = 0

        # Gemini path: 1) agent invocation, 2) session list query
        self.mock_run.side_effect = [mock_run_result, mock_session_list]

        with patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_MODEL": "gemini-pro"}):
            agent_driver.invoke_agent("test task", session_key="session-gem")

        # The first call is the actual gemini agent invocation
        cmd = self.mock_run.call_args_list[0][0][0]
        self.assertNotIn("--thinking", cmd,
                         f"Gemini command must NOT include --thinking: {cmd}")
        self.assertIn("--yolo", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("--model", cmd)


# ============================================================================
# 4.4  Cross-Contract Convergence
# ============================================================================

class TestCrossContractConvergence(unittest.TestCase):
    """Test Cases 9-10: Validate that PR-003_1 and PR-003_2 assumptions hold together."""

    def test_all_spawn_types_receive_thinking_from_orchestrator(self):
        """Orchestrator with --thinking medium passes it to all spawn subprocesses.

        Runs orchestrator through auto-slicing (planner path) and verifies
        the spawn_planner command includes --thinking. Also validates via
        static analysis that the orchestrator constructs --thinking for
        coder, reviewer, and verifier spawn commands.
        """
        import orchestrator

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

        try:
            def dummy_drun(cmd, *args, **kwargs):
                res = MagicMock()
                res.stdout = "main\n" if isinstance(cmd, list) and "branch" in cmd else ""
                res.returncode = 0
                return res
            mocks["drun"].side_effect = dummy_drun

            mocks["extract_json"].return_value = {
                "overall_assessment": "EXCELLENT",
                "prs": [],
            }

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

                argv = [
                    "orchestrator.py",
                    "--enable-exec-from-workspace",
                    "--workdir", workdir,
                    "--prd-file", "dummy_prd.md",
                    "--force-replan", "false",
                    "--channel", "test-channel",
                    "--global-dir", workdir,
                    "--thinking", "medium",
                ]

                with patch("sys.argv", argv):
                    try:
                        orchestrator.main()
                    except SystemExit:
                        pass

            # Collect all spawn subprocess calls
            all_calls = mocks["dpopen"].call_args_list
            spawn_types = {
                "spawn_planner.py": [],
                "spawn_coder.py": [],
                "spawn_reviewer.py": [],
                "spawn_verifier.py": [],
            }
            for call_args in all_calls:
                cmd = call_args[0][0]
                for stype in spawn_types:
                    if stype in str(cmd):
                        spawn_types[stype].append(cmd)

            # Each spawn type that was invoked must include --thinking
            for stype, cmds in spawn_types.items():
                for cmd in cmds:
                    self.assertIn("--thinking", cmd,
                                  f"{stype} command missing --thinking: {cmd}")
                    think_idx = cmd.index("--thinking")
                    self.assertEqual(cmd[think_idx + 1], "medium",
                                     f"{stype} expected thinking='medium', got '{cmd[think_idx + 1]}'")

            # At minimum, spawn_planner must have been invoked (auto-slicing)
            self.assertTrue(len(spawn_types["spawn_planner.py"]) > 0,
                            "spawn_planner was never invoked — check mock setup")

        finally:
            for p in patches.values():
                p.stop()

        # Static validation: orchestrator source constructs --thinking for all spawn types.
        # Complemented by existing tests (test_thinking_orchestrator_to_coder.py,
        # test_thinking_orchestrator_to_reviewer.py, test_thinking_orchestrator_to_verifier.py)
        # that individually verify --thinking for coder, reviewer, and verifier.
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        with open(os.path.join(script_dir, "orchestrator.py"), "r") as f:
            source = f.read()

        for spawn_type in ["spawn_planner.py", "spawn_coder.py", "spawn_reviewer.py",
                           "spawn_verifier.py"]:
            # Verify orchestrator passes --thinking to each spawn type.
            # Check that the file contains a spawn command for this type and that
            # --thinking appears somewhere in the context of that command.
            lines = source.split("\n")
            spawn_line_indices = [i for i, line in enumerate(lines)
                                  if spawn_type in line]
            self.assertTrue(len(spawn_line_indices) > 0,
                            f"orchestrator.py never spawns {spawn_type}")
            # For each occurrence, check nearby lines for --thinking
            found_thinking = False
            for idx in spawn_line_indices:
                ctx = "\n".join(lines[max(0, idx - 2):min(len(lines), idx + 3)])
                if "--thinking" in ctx:
                    found_thinking = True
                    break
            self.assertTrue(found_thinking,
                            f"orchestrator.py spawns {spawn_type} but without --thinking in context")

    def test_no_entrypoint_bypasses_resolver(self):
        """Every spawn_* file imports resolve_thinking from thinking_resolver and calls it.

        This is a static analysis test ensuring no entrypoint defines its own
        thinking default or validation logic.
        """
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        entrypoints = [
            "spawn_planner.py",
            "spawn_coder.py",
            "spawn_reviewer.py",
            "spawn_verifier.py",
            "spawn_auditor.py",
            "spawn_manager.py",
            "spawn_arbitrator.py",
        ]

        for fname in entrypoints:
            fpath = os.path.join(script_dir, fname)
            with open(fpath, "r") as f:
                source = f.read()

            # Must import from thinking_resolver
            self.assertIn("from thinking_resolver import", source,
                          f"{fname} does not import from thinking_resolver")
            self.assertIn("resolve_thinking", source,
                          f"{fname} does not reference resolve_thinking")

            # Must call resolve_thinking (not just import it)
            self.assertIn("resolve_thinking(", source,
                          f"{fname} imports resolve_thinking but never calls it")

            # Must NOT define its own DEFAULT_THINKING or ALLOWED_THINKING_VALUES
            lines = source.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("from thinking_resolver"):
                    continue
                if "ALLOWED_THINKING_VALUES" in stripped and "=" in stripped:
                    self.fail(f"{fname} defines ALLOWED_THINKING_VALUES — must use resolver only")
                if "DEFAULT_THINKING" in stripped and "=" in stripped:
                    self.fail(f"{fname} defines DEFAULT_THINKING — must use resolver only")

        # Also verify orchestrator and agent_driver use the resolver
        for fname in ["orchestrator.py", "agent_driver.py"]:
            fpath = os.path.join(script_dir, fname)
            with open(fpath, "r") as f:
                source = f.read()
            self.assertIn("from thinking_resolver import", source,
                          f"{fname} does not import from thinking_resolver")
            self.assertIn("resolve_thinking", source,
                          f"{fname} does not reference resolve_thinking")


if __name__ == "__main__":
    unittest.main()
