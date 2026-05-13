"""Unit tests for two-phase bootstrap/continue protocol — PR-003."""
import json
import os
import sys
import tempfile as stdlib_tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))

from agent_driver import (
    AgentResult,
    build_bootstrap_prompt,
    capture_gemini_session_id,
    invoke_agent_two_phase,
)
from envelope_assembler import verify_phase2_envelope_integrity


class TestBuildBootstrapPrompt(unittest.TestCase):
    """Test Cases 1-2: bootstrap prompt construction."""

    def test_bootstrap_prompt_is_ultra_thin(self):
        """TC-1: build_bootstrap_prompt() output does NOT contain any main-envelope sections."""
        prompt = build_bootstrap_prompt()
        self.assertNotIn("IDENTITY & PRIMARY GOAL", prompt)
        self.assertNotIn("EXECUTION CONTRACT", prompt)
        self.assertNotIn("REFERENCE INDEX", prompt)
        self.assertNotIn("FINAL CHECKLIST", prompt)

    def test_bootstrap_prompt_is_not_empty(self):
        """TC-2: build_bootstrap_prompt() returns a non-empty string."""
        prompt = build_bootstrap_prompt()
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt.strip()), 0)


class TestCaptureGeminiSessionId(unittest.TestCase):
    """Test Case 3: authoritative session-id capture."""

    def test_capture_gemini_session_id_returns_none_when_no_structured_output(self):
        """TC-3: capture_gemini_session_id returns None when CLI provides no machine-readable session id."""
        result = capture_gemini_session_id("/mock/bin/gemini", "/tmp/mock_prompt.txt")
        self.assertIsNone(result)


class TestTwoPhaseBootstrapMock(unittest.TestCase):
    """Test Cases 4-8, 11: two-phase bootstrap flow with mocked Gemini CLI."""

    def setUp(self):
        self.run_dir = stdlib_tempfile.mkdtemp()
        self.temp_dir = os.path.join(self.run_dir, ".tmp")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.bootstrap_dir = os.path.join(self.run_dir, "bootstrap")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_two_phase_writes_success_artifact_on_bootstrap_ok(self):
        """TC-4: Mocked Gemini CLI success → bootstrap success artifact written with ok=true, authoritative=true."""
        def fake_popen(*args, stdout=None, stderr=None, **kwargs):
            if stdout is not None:
                stdout.write("mock phase 2 output")
                stdout.flush()
            if stderr is not None:
                stderr.write("")
                stderr.flush()
            proc = MagicMock()
            proc.wait.return_value = 0
            return proc

        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            "SDLC_MOCK_SESSION_ID": "sess_auth_001",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.Popen", side_effect=fake_popen):
                    result = invoke_agent_two_phase(
                        "full task envelope", session_key="test-sess", run_dir=self.run_dir
                    )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "test-sess")
        self.assertEqual(result.stdout, "mock phase 2 output")
        self.assertEqual(result.return_code, 0)

        # Verify bootstrap success artifact
        artifacts = os.listdir(self.bootstrap_dir)
        self.assertEqual(len(artifacts), 1)
        artifact_path = os.path.join(self.bootstrap_dir, artifacts[0])
        with open(artifact_path, "r") as f:
            artifact = json.load(f)
        self.assertTrue(artifact["ok"])
        self.assertTrue(artifact["authoritative"])
        self.assertEqual(artifact["resume_handle"], "sess_auth_001")
        self.assertEqual(artifact["engine"], "gemini")
        self.assertEqual(artifact["phase"], "bootstrap")

    def test_two_phase_writes_failure_artifact_on_bootstrap_fail(self):
        """TC-5: Mocked Gemini CLI failure → bootstrap failure artifact written with ok=false."""
        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            # SDLC_MOCK_SESSION_ID deliberately absent → failure
        }
        with patch.dict(os.environ, env, clear=False):
            result = invoke_agent_two_phase(
                "full task envelope", session_key="test-sess", run_dir=self.run_dir
            )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.return_code, 1)
        self.assertIn("missing_authoritative_resume_handle", result.stderr)

        # Verify bootstrap failure artifact
        artifacts = os.listdir(self.bootstrap_dir)
        self.assertEqual(len(artifacts), 1)
        artifact_path = os.path.join(self.bootstrap_dir, artifacts[0])
        with open(artifact_path, "r") as f:
            artifact = json.load(f)
        self.assertFalse(artifact["ok"])
        self.assertFalse(artifact["authoritative"])
        self.assertEqual(artifact["failure_reason"], "missing_authoritative_resume_handle")

    def test_two_phase_phase2_uses_resume_flag(self):
        """TC-6: Mocked bootstrap success → Phase 2 invocation includes -r <session_id> flag."""
        cmd_calls = []

        def fake_popen(*args, **kwargs):
            # Phase 1 (if any) or Phase 2 popen — we only care about Phase 2
            proc = MagicMock()
            proc.wait.return_value = 0
            return proc

        def fake_popen_capture(cmd, stdout=None, stderr=None, start_new_session=None, env=None, **kwargs):
            cmd_calls.append(cmd)
            if stdout is not None:
                stdout.write("phase 2 output")
                stdout.flush()
            if stderr is not None:
                stderr.write("")
                stderr.flush()
            proc = MagicMock()
            proc.wait.return_value = 0
            return proc

        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            "SDLC_MOCK_SESSION_ID": "sess_resume_002",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch(
                    "agent_driver.subprocess.Popen", side_effect=fake_popen_capture
                ):
                    result = invoke_agent_two_phase(
                        "full task envelope", session_key="test-sess", run_dir=self.run_dir
                    )

        self.assertEqual(result.return_code, 0)
        # At least one Popen call; the last one should be Phase 2 with -r flag
        self.assertGreaterEqual(len(cmd_calls), 1)
        phase2_cmd = cmd_calls[-1]
        self.assertIn("-r", phase2_cmd)
        r_idx = phase2_cmd.index("-r")
        self.assertEqual(phase2_cmd[r_idx + 1], "sess_resume_002")

    def test_two_phase_phase2_includes_full_task_envelope(self):
        """TC-7: Mocked bootstrap success → Phase 2 prompt contains the original task_string without bootstrap contamination."""
        task_string = "## IDENTITY & PRIMARY GOAL\nYou are a coder.\n\n## EXECUTION CONTRACT\n- Do work\n\n## REFERENCE INDEX\n[]\n\n## FINAL CHECKLIST\n- Done\n"

        captured_phase2_paths = []
        real_mkstemp = stdlib_tempfile.mkstemp

        def fake_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            prefix = kwargs.get("prefix", "")
            if "sdlc_phase2_" in prefix:
                captured_phase2_paths.append(path)
            return fd, path

        # Prevent cleanup of Phase 2 prompt file so we can inspect it
        real_os_remove = os.remove
        def guarded_remove(p, *args, **kwargs):
            if "sdlc_phase2_" in str(p):
                return  # skip cleanup for test inspection
            return real_os_remove(p, *args, **kwargs)

        def fake_popen(*args, stdout=None, stderr=None, **kwargs):
            if stdout is not None:
                stdout.write("mock phase 2 output")
                stdout.flush()
            if stderr is not None:
                stderr.write("")
                stderr.flush()
            proc = MagicMock()
            proc.wait.return_value = 0
            return proc

        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            "SDLC_MOCK_SESSION_ID": "sess_env_003",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.Popen", side_effect=fake_popen):
                    with patch("agent_driver.tempfile.mkstemp", side_effect=fake_mkstemp):
                        with patch("agent_driver.os.remove", side_effect=guarded_remove):
                            result = invoke_agent_two_phase(
                                task_string, session_key="test-sess", run_dir=self.run_dir
                            )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.return_code, 0)

        # Verify Phase 2 prompt file exists with full task envelope
        self.assertEqual(len(captured_phase2_paths), 1)
        phase2_file = captured_phase2_paths[0]
        with open(phase2_file, "r") as f:
            phase2_content = f.read()

        self.assertIn("IDENTITY & PRIMARY GOAL", phase2_content)
        self.assertIn("EXECUTION CONTRACT", phase2_content)
        self.assertIn("REFERENCE INDEX", phase2_content)
        self.assertNotIn("Phase 1: bootstrap", phase2_content)

    def test_two_phase_aborts_on_bootstrap_failure(self):
        """TC-8: Mocked bootstrap failure → invoke_agent_two_phase returns return_code=1 without attempting Phase 2."""
        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            # SDLC_MOCK_SESSION_ID absent → failure
        }
        with patch.dict(os.environ, env, clear=False):
            result = invoke_agent_two_phase(
                "full task envelope", session_key="test-sess", run_dir=self.run_dir
            )

        self.assertEqual(result.return_code, 1)
        self.assertIn("missing_authoritative_resume_handle", result.stderr)

        # Verify no Phase 2 prompt file exists
        phase2_files = [
            f for f in os.listdir(self.temp_dir)
            if f.startswith("sdlc_phase2_")
        ]
        self.assertEqual(len(phase2_files), 0)

    def test_bootstrap_artifact_index_points_to_correct_invocation(self):
        """TC-11: Mocked bootstrap → verify index artifact resolves to the correct invocation artifact."""
        def fake_popen(*args, stdout=None, stderr=None, **kwargs):
            if stdout is not None:
                stdout.write("mock output")
                stdout.flush()
            if stderr is not None:
                stderr.write("")
                stderr.flush()
            proc = MagicMock()
            proc.wait.return_value = 0
            return proc

        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "mock phase 2 output",
            "SDLC_MOCK_SESSION_ID": "sess_idx_004",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.Popen", side_effect=fake_popen):
                    invoke_agent_two_phase(
                        "full task envelope", session_key="test-sess", run_dir=self.run_dir
                    )

        # Read index artifact
        index_path = os.path.join(self.run_dir, "bootstrap_index.json")
        self.assertTrue(os.path.exists(index_path))
        with open(index_path, "r") as f:
            index = json.load(f)
        self.assertIn("active_targets", index)
        self.assertIn("test-sess", index["active_targets"])

        # Resolve index → artifact
        relative_path = index["active_targets"]["test-sess"]
        artifact_path = os.path.join(self.run_dir, relative_path)
        self.assertTrue(os.path.exists(artifact_path))
        with open(artifact_path, "r") as f:
            artifact = json.load(f)
        self.assertTrue(artifact["ok"])
        self.assertTrue(artifact["authoritative"])


class TestPhase2EnvelopeIntegrity(unittest.TestCase):
    """Test Cases 9-10: Phase 2 envelope integrity validation."""

    def test_verify_phase2_envelope_integrity_passes_for_full_envelope(self):
        """TC-9: verify_phase2_envelope_integrity(full_envelope_prompt) returns True."""
        full_envelope = (
            "## IDENTITY & PRIMARY GOAL\n"
            "You are a coder.\n\n"
            "## OPERATING CONSTRAINTS\n"
            "- Do not git push.\n\n"
            "## EXECUTION CONTRACT\n"
            "- Locked Working Directory: /workspace\n\n"
            "## REFERENCE INDEX\n"
            '[{"id": "pr_contract", "kind": "pr_contract"}]\n\n'
            "## FINAL CHECKLIST\n"
            "- Report latest commit hash\n\n"
            "## START WORK\n"
            "As the CODER, begin your task now.\n"
        )
        self.assertTrue(verify_phase2_envelope_integrity(full_envelope))

    def test_verify_phase2_envelope_integrity_fails_for_thin_prompt(self):
        """TC-10: verify_phase2_envelope_integrity(bootstrap_prompt) returns False."""
        bootstrap_prompt = build_bootstrap_prompt()
        self.assertFalse(verify_phase2_envelope_integrity(bootstrap_prompt))

    def test_verify_phase2_envelope_integrity_fails_for_missing_sections(self):
        """verify_phase2_envelope_integrity returns False when a required section is missing."""
        incomplete = (
            "## IDENTITY & PRIMARY GOAL\n"
            "You are a coder.\n\n"
            "## EXECUTION CONTRACT\n"
            "- Do work.\n"
            # Missing REFERENCE INDEX
        )
        self.assertFalse(verify_phase2_envelope_integrity(incomplete))

    def test_verify_phase2_envelope_integrity_detects_bootstrap_contamination(self):
        """verify_phase2_envelope_integrity returns False when bootstrap markers are present."""
        contaminated = (
            "## IDENTITY & PRIMARY GOAL\n"
            "You are a coder.\n\n"
            "## EXECUTION CONTRACT\n"
            "- Do work.\n\n"
            "## REFERENCE INDEX\n"
            '[{"id": "pr_contract"}]\n\n'
            "Phase 1: bootstrap\n"  # Bootstrap contamination
        )
        self.assertFalse(verify_phase2_envelope_integrity(contaminated))


class TestLegacyInvokeAgentUnchanged(unittest.TestCase):
    """Test Case 12: existing invoke_agent() behavior is unchanged."""

    def test_existing_invoke_agent_unchanged(self):
        """TC-12: existing invoke_agent() behavior is unchanged by this PR — legacy path still works."""
        from agent_driver import invoke_agent

        env = {
            "LLM_DRIVER": "gemini",
            "SDLC_MOCK_LLM_RESPONSE": "legacy output",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("agent_driver.resolve_cmd", return_value="/mock/bin/gemini"):
                with patch("agent_driver.subprocess.run", return_value=MagicMock(returncode=0, stdout="[]", stderr="")):
                    with patch("agent_driver.subprocess.Popen") as mock_popen:
                        proc = MagicMock()
                        proc.wait.return_value = 0
                        mock_popen.return_value = proc
                        result = invoke_agent(
                            "legacy task", session_key="legacy-sess"
                        )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.session_key, "legacy-sess")
        self.assertEqual(result.stdout, "legacy output")
        self.assertEqual(result.return_code, 0)


if __name__ == "__main__":
    unittest.main()
