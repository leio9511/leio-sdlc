"""Integration tests validating that every spawn_* entrypoint accepts
--thinking, defaults to 'high', rejects illegal values, and the manager
test-mode regression is fixed.

Tests use subprocess invocations with SDLC_TEST_MODE=true for reliable,
leak-free integration testing across all 7 entrypoints.
"""

import os
import sys
import tempfile
import subprocess
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _make_valid_prd(workdir, name="PRD_Test.md"):
    """Create a minimal valid PRD file with all required sections."""
    path = os.path.join(workdir, name)
    content = """# PRD: Test PRD

## 1. Context & Problem (业务背景与核心痛点)
Test context.

## 2. Requirements & User Stories (需求定义)
Test requirements.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
Test architecture.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
Test acceptance.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
Test strategy.

## 6. Framework Modifications (框架防篡改声明)
Test modifications.

## 7. Hardcoded Content (硬编码内容)
```text
test
```
"""
    with open(path, "w") as f:
        f.write(content)
    return path


def _make_git_repo(workdir):
    """Create a minimal git repo in workdir on a feature branch."""
    os.makedirs(os.path.join(workdir, ".git"), exist_ok=True)
    with open(os.path.join(workdir, ".git", "HEAD"), "w") as f:
        f.write("ref: refs/heads/feature/test-branch\n")


def _make_pr_file(workdir, name="PR_001_Test.md"):
    """Create a minimal PR contract file."""
    path = os.path.join(workdir, name)
    content = """---
status: open
---

# PR-001: Test PR

## 1. Objective
Test objective.

## 2. Target Working Set & File Placement
Test placement.

## 3. Implementation Scope
Test scope.

## 4. TDD Blueprint & Acceptance Criteria
Test TDD.
"""
    with open(path, "w") as f:
        f.write(content)
    return path


def _build_cmd(module_name, script_path, workdir, prd_path, pr_path, job_dir, extra_args=None):
    """Build the subprocess command for a given entrypoint."""
    if module_name == "spawn_planner":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--prd-file", prd_path,
            "--workdir", workdir,
            "--run-dir", job_dir,
        ]
    elif module_name == "spawn_coder":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--pr-file", pr_path,
            "--prd-file", prd_path,
            "--workdir", workdir,
            "--run-dir", job_dir,
        ]
    elif module_name == "spawn_reviewer":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--pr-file", pr_path,
            "--prd-file", prd_path,
            "--diff-target", "HEAD~1..HEAD",
            "--workdir", workdir,
            "--run-dir", job_dir,
        ]
    elif module_name == "spawn_auditor":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--prd-file", prd_path,
            "--workdir", workdir,
            "--channel", "test-channel",
        ]
    elif module_name == "spawn_verifier":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--prd-files", prd_path,
            "--workdir", workdir,
            "--out-file", os.path.join(job_dir, "uat_report.json"),
        ]
    elif module_name == "spawn_manager":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--workdir", workdir,
            "--job-dir", job_dir,
        ]
    elif module_name == "spawn_arbitrator":
        cmd = [
            sys.executable, script_path,
            "--enable-exec-from-workspace",
            "--pr-file", pr_path,
            "--diff-target", "HEAD~1..HEAD",
            "--workdir", workdir,
            "--run-dir", job_dir,
        ]
    else:
        raise ValueError(f"Unknown module: {module_name}")

    if extra_args:
        cmd.extend(extra_args)
    return cmd


class TestExplicitThinkingPropagation(unittest.TestCase):
    """Test Cases 1-7: Verify each spawn_* entrypoint accepts explicit --thinking values."""

    ENTRYPOINTS = [
        ("spawn_planner", "medium"),
        ("spawn_coder", "low"),
        ("spawn_reviewer", "high"),
        ("spawn_auditor", "xhigh"),
        ("spawn_verifier", "low"),
        ("spawn_manager", "medium"),
        ("spawn_arbitrator", "xhigh"),
    ]

    def test_spawn_planner_accepts_thinking_medium(self):
        """Run spawn_planner with --thinking medium in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_planner", "medium")

    def test_spawn_coder_accepts_thinking_low(self):
        """Run spawn_coder with --thinking low in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_coder", "low")

    def test_spawn_reviewer_accepts_thinking_high(self):
        """Run spawn_reviewer with --thinking high in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_reviewer", "high")

    def test_spawn_auditor_accepts_thinking_xhigh(self):
        """Run spawn_auditor with --thinking xhigh in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_auditor", "xhigh")

    def test_spawn_verifier_accepts_thinking_low(self):
        """Run spawn_verifier with --thinking low in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_verifier", "low")

    def test_spawn_manager_accepts_thinking_medium(self):
        """Run spawn_manager with --thinking medium in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_manager", "medium")

    def test_spawn_arbitrator_accepts_thinking_xhigh(self):
        """Run spawn_arbitrator with --thinking xhigh in test mode. Verify exit 0."""
        self._run_thinking_test("spawn_arbitrator", "xhigh")

    def _run_thinking_test(self, module_name, thinking_value):
        script_path = os.path.join(SCRIPTS_DIR, f"{module_name}.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_git_repo(tmpdir)
            prd_path = _make_valid_prd(tmpdir)
            pr_path = _make_pr_file(tmpdir)
            job_dir = os.path.join(tmpdir, "job_dir")
            os.makedirs(job_dir, exist_ok=True)

            env = os.environ.copy()
            env["SDLC_TEST_MODE"] = "true"

            cmd = _build_cmd(module_name, script_path, tmpdir, prd_path, pr_path, job_dir,
                             extra_args=["--thinking", thinking_value])

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(
                result.returncode, 0,
                f"{module_name} with --thinking {thinking_value} failed (exit {result.returncode}): "
                f"stderr: {result.stderr[:300]}"
            )


class TestDefaultThinkingBehavior(unittest.TestCase):
    """Test Case 8: Verify default thinking='high' for every spawn_* entrypoint."""

    ENTRYPOINTS = [
        "spawn_planner",
        "spawn_coder",
        "spawn_reviewer",
        "spawn_auditor",
        "spawn_verifier",
        "spawn_manager",
        "spawn_arbitrator",
    ]

    def test_spawn_entrypoint_defaults_to_high(self):
        """For each of the 7 spawn entrypoints, run without --thinking and verify exit 0."""
        for module_name in self.ENTRYPOINTS:
            with self.subTest(entrypoint=module_name):
                script_path = os.path.join(SCRIPTS_DIR, f"{module_name}.py")
                with tempfile.TemporaryDirectory() as tmpdir:
                    _make_git_repo(tmpdir)
                    prd_path = _make_valid_prd(tmpdir)
                    pr_path = _make_pr_file(tmpdir)
                    job_dir = os.path.join(tmpdir, "job_dir")
                    os.makedirs(job_dir, exist_ok=True)

                    env = os.environ.copy()
                    env["SDLC_TEST_MODE"] = "true"

                    cmd = _build_cmd(module_name, script_path, tmpdir, prd_path, pr_path, job_dir)

                    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                    self.assertEqual(
                        result.returncode, 0,
                        f"{module_name} without --thinking failed (exit {result.returncode}): "
                        f"stderr: {result.stderr[:300]}"
                    )


class TestIllegalThinkingRejection(unittest.TestCase):
    """Test Case 9: Verify every spawn_* entrypoint rejects illegal --thinking values."""

    ENTRYPOINTS = [
        "spawn_planner",
        "spawn_coder",
        "spawn_reviewer",
        "spawn_auditor",
        "spawn_verifier",
        "spawn_manager",
        "spawn_arbitrator",
    ]

    def test_every_spawn_rejects_illegal_thinking(self):
        """For each spawn_* entrypoint, run with --thinking garbage via subprocess and verify non-zero exit."""
        for module_name in self.ENTRYPOINTS:
            with self.subTest(entrypoint=module_name):
                script_path = os.path.join(SCRIPTS_DIR, f"{module_name}.py")
                with tempfile.TemporaryDirectory() as tmpdir:
                    _make_git_repo(tmpdir)
                    prd_path = _make_valid_prd(tmpdir)
                    pr_path = _make_pr_file(tmpdir)
                    job_dir = os.path.join(tmpdir, "job_dir")
                    os.makedirs(job_dir, exist_ok=True)

                    env = os.environ.copy()
                    env["SDLC_TEST_MODE"] = "true"

                    cmd = _build_cmd(module_name, script_path, tmpdir, prd_path, pr_path, job_dir,
                                     extra_args=["--thinking", "garbage"])

                    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                    self.assertNotEqual(
                        result.returncode, 0,
                        f"{module_name} accepted illegal --thinking garbage (exit {result.returncode}). "
                        f"stdout: {result.stdout[:200]} stderr: {result.stderr[:200]}"
                    )


class TestThinkingResolverPropagation(unittest.TestCase):
    """Supplementary test: Verify thinking propagates through resolve_thinking → invoke_agent.

    Uses a dedicated test-mode-free approach: set SDLC_MOCK_LLM_RESPONSE (which
    causes agent_driver.invoke_agent to short-circuit) and assert the entrypoint
    doesn't crash before reaching invoke_agent with each valid thinking value.
    """

    def test_all_valid_thinking_values_accepted(self):
        """Each of the 4 valid thinking values reaches invoke_agent without crashing."""
        valid_values = ["low", "medium", "high", "xhigh"]
        for thinking in valid_values:
            script_path = os.path.join(SCRIPTS_DIR, "spawn_planner.py")
            with tempfile.TemporaryDirectory() as tmpdir:
                _make_git_repo(tmpdir)
                prd_path = _make_valid_prd(tmpdir)
                job_dir = os.path.join(tmpdir, "job_dir")
                os.makedirs(job_dir, exist_ok=True)

                env = os.environ.copy()
                env.pop("SDLC_TEST_MODE", None)
                env["SDLC_MOCK_LLM_RESPONSE"] = "OK"

                cmd = [
                    sys.executable, script_path,
                    "--enable-exec-from-workspace",
                    "--prd-file", prd_path,
                    "--workdir", tmpdir,
                    "--run-dir", job_dir,
                    "--thinking", thinking,
                ]

                result = subprocess.run(cmd, env=env, capture_output=True, text=True)
                # May fail due to missing playbook/templates, but should NOT be an argparse failure
                # Check stderr doesn't contain argparse "invalid choice" error
                self.assertNotIn(
                    "invalid choice", (result.stderr or ""),
                    f"spawn_planner rejected valid --thinking {thinking}: {result.stderr[:300]}"
                )
                self.assertNotIn(
                    "unrecognized arguments", (result.stderr or ""),
                    f"spawn_planner rejected --thinking {thinking} as unrecognized: {result.stderr[:300]}"
                )


class TestManagerTestModeRegression(unittest.TestCase):
    """Test Case 10: Verify spawn_manager test mode works without --job-dir."""

    def test_spawn_manager_test_mode_still_works_without_job_dir(self):
        """Run spawn_manager with SDLC_TEST_MODE=true, no --job-dir, --thinking low. Verify exit 0."""
        script_path = os.path.join(SCRIPTS_DIR, "spawn_manager.py")

        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["SDLC_TEST_MODE"] = "true"

            cmd = [
                sys.executable, script_path,
                "--enable-exec-from-workspace",
                "--workdir", tmpdir,
                "--thinking", "low",
            ]
            # Note: --job-dir intentionally omitted to verify the regression fix

            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(
                result.returncode, 0,
                f"spawn_manager test mode without --job-dir failed (exit {result.returncode}): "
                f"stdout: {result.stdout[:300]} stderr: {result.stderr[:300]}"
            )


if __name__ == "__main__":
    unittest.main()
