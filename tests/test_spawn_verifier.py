import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))


class TestSpawnVerifier(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.mkdtemp()
        self.workdir = os.path.join(self.temp_dir, "work")
        self.run_dir = os.path.join(self.temp_dir, "run")
        os.makedirs(self.workdir)
        os.makedirs(self.run_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir)

    def _invoke_spawn_verifier(self, extra_env=None, mock_result=None):
        import spawn_verifier
        from agent_driver import AgentResult

        out_file = os.path.join(self.workdir, "uat_report.json")
        env = {
            "SDLC_TEST_MODE": "false",
            "SDLC_RUN_DIR": self.run_dir,
        }
        if extra_env:
            env.update(extra_env)

        test_args = [
            "spawn_verifier.py",
            "--prd-files",
            "PRD1.md,PRD2.md",
            "--workdir",
            self.workdir,
            "--out-file",
            out_file,
            "--enable-exec-from-workspace",
        ]

        if mock_result is None:
            mock_result = AgentResult(session_key="subtask-verifier", stdout="dummy")

        with patch("spawn_verifier.invoke_agent") as mock_invoke_agent, \
             patch("utils_api_key.setup_spawner_api_key") as mock_setup_key, \
             patch.object(sys, "argv", test_args), \
             patch.dict(os.environ, env, clear=False):
            mock_invoke_agent.return_value = mock_result
            if env.get("SDLC_TEST_MODE", "").lower() != "true":
                with open(out_file, "w") as f:
                    f.write('{"status": "PASS", "executive_summary": "precreated", "verification_details": []}')
            spawn_verifier.main()

        return out_file, mock_invoke_agent, mock_setup_key

    def test_spawn_verifier_uses_envelope_prompt_and_saves_uat_debug_artifacts(self):
        out_file, mock_invoke_agent, mock_setup_key = self._invoke_spawn_verifier()

        self.assertTrue(mock_invoke_agent.called, "invoke_agent was not called for verifier")
        args, kwargs = mock_invoke_agent.call_args
        rendered_prompt = args[0]
        self.assertTrue(rendered_prompt.startswith("# EXECUTION CONTRACT"))
        self.assertEqual(kwargs.get("role"), "verifier")
        mock_setup_key.assert_called()

        debug_dir = os.path.join(self.run_dir, "uat_debug", "initial")
        startup_packet_path = os.path.join(debug_dir, "startup_packet.json")
        rendered_prompt_path = os.path.join(debug_dir, "rendered_prompt.txt")
        self.assertTrue(os.path.exists(startup_packet_path))
        self.assertTrue(os.path.exists(rendered_prompt_path))

        with open(startup_packet_path, "r") as f:
            startup_packet = json.load(f)
        self.assertEqual(startup_packet["role"], "verifier")
        prd_refs = [ref["path"] for ref in startup_packet["reference_index"] if ref["kind"] == "prd"]
        self.assertEqual(prd_refs, ["PRD1.md", "PRD2.md"])

        with open(rendered_prompt_path, "r") as f:
            saved_prompt = f.read()
        self.assertEqual(saved_prompt, rendered_prompt)
        self.assertTrue(os.path.exists(out_file))

    def test_spawn_verifier_no_longer_uses_legacy_build_prompt(self):
        import agent_driver
        import spawn_verifier

        with patch.object(agent_driver, "build_prompt", side_effect=AssertionError("legacy build_prompt must not be called")) as mock_build_prompt:
            out_file, mock_invoke_agent, _ = self._invoke_spawn_verifier()

        self.assertFalse(hasattr(spawn_verifier, "build_prompt"))
        mock_build_prompt.assert_not_called()
        prompt = mock_invoke_agent.call_args.args[0]
        self.assertIn("# REFERENCE INDEX", prompt)
        self.assertNotIn("ATTENTION: Your root workspace is rigidly locked", prompt)
        self.assertTrue(os.path.exists(out_file))

    def test_spawn_verifier_test_mode_preserves_mock_output_and_logs_rendered_prompt(self):
        mock_json = '{"status": "NEEDS_FIX", "executive_summary": "Mock failed", "verification_details": []}'
        out_file, mock_invoke_agent, _ = self._invoke_spawn_verifier(
            extra_env={
                "SDLC_TEST_MODE": "true",
                "MOCK_VERIFIER_RESULT": mock_json,
            }
        )

        mock_invoke_agent.assert_not_called()
        with open(out_file, "r") as f:
            self.assertEqual(f.read(), mock_json)

        task_log_path = os.path.join(self.run_dir, "tests", "verifier_task_string.log")
        with open(task_log_path, "r") as f:
            task_log = f.read()
        self.assertTrue(task_log.startswith("# EXECUTION CONTRACT"))

        debug_dir = os.path.join(self.run_dir, "uat_debug", "initial")
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_packet.json")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "rendered_prompt.txt")))

    def test_verifier_legacy_prompt_entry_is_deprecated(self):
        prompts_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "prompts.json"))
        with open(prompts_path, "r") as f:
            prompts = json.load(f)

        self.assertEqual(
            prompts["verifier"],
            "__DEPRECATED__ use envelope_assembler.py — see spawn_verifier.py",
        )

    def test_verifier_playbook_contains_startup_protocol(self):
        playbook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks", "verifier_playbook.md"))
        with open(playbook_path, "r") as f:
            playbook = f.read()

        self.assertIn("## Startup Protocol", playbook)
        self.assertIn("Contract-First Priority", playbook)
        self.assertIn("Required Reference-Read Rule", playbook)
        self.assertIn("Read-Only (EMPHASIZED)", playbook)
        self.assertIn("Output Contract", playbook)

    def test_verifier_aligned_to_file_based_result(self):
        from agent_driver import AgentResult

        mock_result = AgentResult(
            session_key="subtask-verifier",
            stdout="Here is my reasoning. I have written the uat_report.json file.",
        )
        try:
            out_file, mock_invoke_agent, _ = self._invoke_spawn_verifier(mock_result=mock_result)
        except SystemExit as e:
            self.fail(f"spawn_verifier.main() exited unexpectedly with code {e.code} despite out-file existing")

        self.assertTrue(mock_invoke_agent.called)
        self.assertTrue(os.path.exists(out_file))


if __name__ == '__main__':
    unittest.main()
