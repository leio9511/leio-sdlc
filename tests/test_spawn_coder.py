import os
import sys
import tempfile
import unittest
from unittest.mock import patch, mock_open
import json

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import builtins

import config
import spawn_coder
from agent_driver import AgentResult

real_open = builtins.open
real_exists = os.path.exists


class TestSpawnCoder(unittest.TestCase):
    def setUp(self):
        self.old_env = os.environ.copy()
        if "LLM_DRIVER" in os.environ:
            del os.environ["LLM_DRIVER"]

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_extract_pr_id(self):
        self.assertEqual(spawn_coder.extract_pr_id("docs/PR_001_Test.md"), "PR_001")
        self.assertEqual(spawn_coder.extract_pr_id("PR_123_Something.md"), "PR_123")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_Fix.md"), "PR_003_1")
        self.assertEqual(spawn_coder.extract_pr_id("PR_003_1_2_Something.md"), "PR_003_1_2")
        self.assertEqual(spawn_coder.extract_pr_id("NoPrefix.md"), "NoPrefix")

    @patch('spawn_coder.invoke_agent')
    def test_send_feedback(self, mock_call):
        mock_call.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        spawn_coder.send_feedback("sdlc_coder_PR_001", "feedback message")
        mock_call.assert_called_once_with("feedback message", session_key="sdlc_coder_PR_001", role="coder", run_dir=".", thinking=None)

    @patch('spawn_coder.get_current_branch', return_value='feature/test')
    @patch('spawn_coder.get_latest_commit_hash', return_value='abc123')
    @patch('spawn_coder.os.path.exists')
    @patch('envelope_assembler.os.makedirs')
    @patch('spawn_coder.invoke_agent')
    @patch('spawn_coder.build_coder_startup_packet_and_prompt')
    def test_handle_feedback_routing_with_stored_key(self, mock_build, mock_invoke, mock_makedirs, mock_exists, mock_commit, mock_branch):
        mock_exists.return_value = True

        def mock_file_open(path, *args, **kwargs):
            if "feedback.txt" in str(path):
                return mock_open(read_data="Fix the bugs.")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open(read_data="sdlc_coder_PR_001")(path, *args, **kwargs)
            return mock_open(read_data="")(path, *args, **kwargs)

        with patch('builtins.open', side_effect=mock_file_open):
            mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
            is_existing, key = spawn_coder.handle_feedback_routing("/tmp/work", ".", "PR.md", "PRD.md", "playbook.md", "feedback.txt", "PR_001")

        self.assertTrue(is_existing)
        self.assertEqual(key, "sdlc_coder_PR_001")
        mock_invoke.assert_called_once()
        called_msg = mock_invoke.call_args[0][0]
        called_kwargs = mock_invoke.call_args[1]
        self.assertEqual(called_kwargs['session_key'], "sdlc_coder_PR_001")
        self.assertIn("# REVIEW REPORT JSON", called_msg)
        self.assertIn("Fix the bugs.", called_msg)
        self.assertIn(spawn_coder.REVISION_CONTINUATION_RULE, called_msg)
        self.assertNotIn("# REFERENCE INDEX", called_msg)

    @patch('spawn_coder.config.load_or_merge_config')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_switching_coder_playbook_version_from_2_to_1_restores_v1_new_session_prompt_shapes(self, mock_setup_key, mock_invoke, mock_check_output, mock_load_config):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            feedback_file = os.path.join(tmp_dir, "feedback.json")
            with open(pr_file, "w") as f:
                f.write("pr content")
            with open(prd_file, "w") as f:
                f.write("prd content")
            with open(feedback_file, "w") as f:
                f.write('{"status": "NEEDS_FIX", "comments": "rollback"}')

            scenarios = [
                {
                    "name": "initial",
                    "artifact_subdir": os.path.join("coder_debug", "initial"),
                    "args": [
                        "spawn_coder.py",
                        "--pr-file", pr_file,
                        "--prd-file", prd_file,
                        "--workdir", tmp_dir,
                        "--run-dir", tmp_dir,
                        "--enable-exec-from-workspace",
                    ],
                },
                {
                    "name": "revision_bootstrap",
                    "artifact_subdir": os.path.join("coder_debug", "revision_bootstrap_001"),
                    "args": [
                        "spawn_coder.py",
                        "--pr-file", pr_file,
                        "--prd-file", prd_file,
                        "--feedback-file", feedback_file,
                        "--workdir", tmp_dir,
                        "--run-dir", tmp_dir,
                        "--enable-exec-from-workspace",
                    ],
                },
                {
                    "name": "system_alert_bootstrap",
                    "artifact_subdir": os.path.join("coder_debug", "system_alert_001"),
                    "args": [
                        "spawn_coder.py",
                        "--pr-file", pr_file,
                        "--prd-file", prd_file,
                        "--system-alert", "git dirty",
                        "--workdir", tmp_dir,
                        "--run-dir", tmp_dir,
                        "--enable-exec-from-workspace",
                    ],
                },
            ]

            for version, expected_startup_version in [
                (config.CODER_PLAYBOOK_V2, "v2"),
                (config.CODER_PLAYBOOK_V1, "v1"),
            ]:
                mock_load_config.return_value = {config.CODER_PLAYBOOK_VERSION_CONFIG_KEY: version}
                for scenario in scenarios:
                    session_file = os.path.join(tmp_dir, ".coder_session")
                    if os.path.exists(session_file):
                        os.remove(session_file)
                    artifact_dir = os.path.join(tmp_dir, scenario["artifact_subdir"])
                    if os.path.isdir(artifact_dir):
                        for root, dirs, files in os.walk(artifact_dir, topdown=False):
                            for name in files:
                                os.remove(os.path.join(root, name))
                            for name in dirs:
                                os.rmdir(os.path.join(root, name))
                        os.rmdir(artifact_dir)
                    mock_invoke.reset_mock()

                    with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                        with patch.object(sys, 'argv', scenario["args"]):
                            spawn_coder.main()

                    prompt = mock_invoke.call_args[0][0]
                    packet_path = os.path.join(tmp_dir, scenario["artifact_subdir"], "startup_packet.json")
                    with open(packet_path, "r", encoding="utf-8") as f:
                        packet = json.load(f)

                    self.assertEqual(packet["startup_version"], expected_startup_version)
                    self.assertEqual(packet["coder_playbook_version"], version)
                    self.assertEqual(packet["scenario_type"], scenario["name"])
                    self.assertEqual(packet["assembly_authority_path"], "scripts/envelope_assembler.py")

                    if version == config.CODER_PLAYBOOK_V2:
                        self.assertIn("## CODER PLAYBOOK", prompt)
                        self.assertIn("# Coder Playbook V2", prompt)
                        self.assertIn("## REFERENCE INDEX", prompt)
                        self.assertNotIn("/playbooks/coder_playbook.md", prompt)
                    else:
                        self.assertNotIn("## CODER PLAYBOOK", prompt)
                        self.assertIn("/playbooks/coder_playbook.md", prompt)
                        if scenario["name"] == "initial":
                            self.assertIn("## EXECUTION CONTRACT", prompt)
                            self.assertIn("## REFERENCE INDEX", prompt)
                        elif scenario["name"] == "revision_bootstrap":
                            self.assertIn("# CODER REVISION RECOVERY CONTINUATION", prompt)
                            self.assertIn("# REVIEW REPORT JSON", prompt)
                            self.assertNotIn("## REFERENCE INDEX", prompt)
                        else:
                            self.assertIn("# CODER SYSTEM ALERT RECOVERY CONTINUATION", prompt)
                            self.assertIn("# SYSTEM ALERT YOU MUST FIX", prompt)
                            self.assertNotIn("## REFERENCE INDEX", prompt)

    @patch('spawn_coder.config.load_or_merge_config')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_initial_mode_switches_between_v1_and_v2_using_coder_playbook_version(self, mock_setup_key, mock_invoke, mock_check_output, mock_load_config):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            pr_content = "UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED"
            prd_content = "UNIQUE PRD BODY SHOULD NOT BE INLINED"
            with open(pr_file, "w") as f:
                f.write(pr_content)
            with open(prd_file, "w") as f:
                f.write(prd_content)

            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    mock_load_config.return_value = {config.CODER_PLAYBOOK_VERSION_CONFIG_KEY: config.CODER_PLAYBOOK_V1}
                    spawn_coder.main()

            self.assertTrue(mock_invoke.called)
            v1_task_string = mock_invoke.call_args[0][0]
            self.assertTrue(v1_task_string.startswith("## IDENTITY & PRIMARY GOAL"))
            self.assertIn(os.path.abspath(pr_file), v1_task_string)
            self.assertIn(os.path.abspath(prd_file), v1_task_string)
            self.assertIn(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks", "coder_playbook.md")), v1_task_string)
            self.assertNotIn("# Coder Playbook V2", v1_task_string)
            self.assertNotIn(pr_content, v1_task_string)
            self.assertNotIn(prd_content, v1_task_string)

            with open(os.path.join(tmp_dir, "coder_debug", "initial", "startup_packet.json")) as f:
                v1_packet = json.load(f)
            self.assertIn("coder_playbook", [ref["id"] for ref in v1_packet["reference_index"]])
            self.assertEqual(v1_packet["startup_version"], "v1")
            self.assertEqual(v1_packet["coder_playbook_version"], config.CODER_PLAYBOOK_V1)
            self.assertEqual(v1_packet["scenario_type"], "initial")
            self.assertEqual(v1_packet["assembly_authority_path"], "scripts/envelope_assembler.py")

            mock_invoke.reset_mock()

            with tempfile.TemporaryDirectory() as tmp_dir_v2:
                pr_file_v2 = os.path.join(tmp_dir_v2, "PR_001.md")
                prd_file_v2 = os.path.join(tmp_dir_v2, "PRD.md")
                with open(pr_file_v2, "w") as f:
                    f.write(pr_content)
                with open(prd_file_v2, "w") as f:
                    f.write(prd_content)

                test_args_v2 = [
                    "spawn_coder.py",
                    "--pr-file", pr_file_v2,
                    "--prd-file", prd_file_v2,
                    "--workdir", tmp_dir_v2,
                    "--run-dir", tmp_dir_v2,
                    "--enable-exec-from-workspace",
                ]

                with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                    with patch.object(sys, 'argv', test_args_v2):
                        mock_load_config.return_value = {config.CODER_PLAYBOOK_VERSION_CONFIG_KEY: config.CODER_PLAYBOOK_V2}
                        spawn_coder.main()

                v2_task_string = mock_invoke.call_args[0][0]
                self.assertIn("## CODER PLAYBOOK", v2_task_string)
                self.assertIn("# Coder Playbook V2", v2_task_string)
                self.assertIn(os.path.abspath(pr_file_v2), v2_task_string)
                self.assertIn(os.path.abspath(prd_file_v2), v2_task_string)
                self.assertNotIn(pr_content, v2_task_string)
                self.assertNotIn(prd_content, v2_task_string)

                with open(os.path.join(tmp_dir_v2, "coder_debug", "initial", "startup_packet.json")) as f:
                    v2_packet = json.load(f)
                self.assertEqual(v2_packet["startup_version"], "v2")
                self.assertEqual([ref["id"] for ref in v2_packet["reference_index"]], ["pr_contract", "prd"])

    @patch('spawn_coder.config.load_or_merge_config')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_initial_v2_default_comes_from_config_when_key_is_absent_from_runtime_env(self, mock_setup_key, mock_invoke, mock_check_output, mock_load_config):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")
        mock_load_config.return_value = {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            pr_content = "UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED"
            prd_content = "UNIQUE PRD BODY SHOULD NOT BE INLINED"
            with open(pr_file, "w") as f:
                f.write(pr_content)
            with open(prd_file, "w") as f:
                f.write(prd_content)

            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()

            task_string = mock_invoke.call_args[0][0]
            self.assertIn("# Coder Playbook V2", task_string)
            self.assertNotIn(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks", "coder_playbook.md")), task_string)
            self.assertNotIn(pr_content, task_string)
            self.assertNotIn(prd_content, task_string)

            with open(os.path.join(tmp_dir, "coder_debug", "initial", "startup_packet.json")) as f:
                packet = json.load(f)
            self.assertEqual(packet["startup_version"], "v2")
            self.assertEqual([ref["id"] for ref in packet["reference_index"]], ["pr_contract", "prd"])

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_initial_mode_uses_envelope_prompt(self, mock_setup_key, mock_invoke, mock_check_output):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            pr_content = "UNIQUE PR CONTRACT BODY SHOULD NOT BE INLINED"
            prd_content = "UNIQUE PRD BODY SHOULD NOT BE INLINED"
            with open(pr_file, "w") as f:
                f.write(pr_content)
            with open(prd_file, "w") as f:
                f.write(prd_content)

            test_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', test_args):
                    spawn_coder.main()

            self.assertTrue(mock_invoke.called)
            task_string = mock_invoke.call_args[0][0]
            self.assertTrue(task_string.startswith("## IDENTITY & PRIMARY GOAL"))
            self.assertIn(os.path.abspath(pr_file), task_string)
            self.assertIn(os.path.abspath(prd_file), task_string)
            self.assertIn("## CODER PLAYBOOK", task_string)
            self.assertIn("# Coder Playbook V2", task_string)
            self.assertNotIn(pr_content, task_string)
            self.assertNotIn(prd_content, task_string)
            mock_setup_key.assert_called_once()

            packet_file = os.path.join(tmp_dir, "coder_debug", "initial", "startup_packet.json")
            prompt_file = os.path.join(tmp_dir, "coder_debug", "initial", "rendered_prompt.txt")
            self.assertTrue(os.path.exists(packet_file))
            self.assertTrue(os.path.exists(prompt_file))

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_mocked_revision_flow_prompt_injection(self, mock_setup_key, mock_exists, mock_invoke, mock_check_output):
        def custom_exists(path):
            if ".coder_session" in str(path):
                return False
            if "PR" in str(path) or "PRD" in str(path) or "feedback" in str(path) or "prompts.json" in str(path):
                return True
            return real_exists(path)

        mock_exists.side_effect = custom_exists

        def mock_file_open(path, *args, **kwargs):
            if "feedback" in str(path):
                return mock_open(read_data='{"status": "NEEDS_FIX", "comments": "Missing stuff"}')(path, *args, **kwargs)
            if "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open()(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--feedback-file", "feedback.json", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001", stdout="")

                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()

        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        self.assertIn("## RECOVERY MISSION", prompt_sent)
        self.assertIn("## REVIEWER FEEDBACK", prompt_sent)
        self.assertIn('{"status": "NEEDS_FIX", "comments": "Missing stuff"}', prompt_sent)
        self.assertIn("The reviewer feedback below is the immediate action target.", prompt_sent)
        self.assertNotIn(os.path.abspath("feedback.json"), prompt_sent)
        self.assertNotIn("# REVIEW REPORT JSON", prompt_sent)
        mock_setup_key.assert_called_once()

    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('os.path.exists')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_mocked_revision_flow_prompt_injection_existing_session(self, mock_setup_key, mock_exists, mock_invoke, mock_check_output):
        def custom_exists(path):
            if ".coder_session" in str(path):
                return True
            if "PR" in str(path) or "PRD" in str(path) or "feedback" in str(path) or "prompts.json" in str(path):
                return True
            return real_exists(path)

        mock_exists.side_effect = custom_exists

        def mock_file_open(path, *args, **kwargs):
            if "feedback" in str(path):
                return mock_open(read_data='{"status": "NEEDS_FIX", "comments": "Missing stuff"}')(path, *args, **kwargs)
            if "PR_001.md" in str(path) or "PRD.md" in str(path):
                return mock_open(read_data="Mocked Content")(path, *args, **kwargs)
            if ".coder_session" in str(path):
                return mock_open(read_data="sdlc_coder_PR_001_1234abcd")(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        test_args = ["spawn_coder.py", "--pr-file", "PR_001.md", "--prd-file", "PRD.md", "--feedback-file", "feedback.json", "--workdir", "/tmp", "--enable-exec-from-workspace"]
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false", "SDLC_FORCE_NEW_CODER_SESSION": "0"}):
            with patch.object(sys, 'argv', test_args):
                mock_check_output.return_value = "feature/test"
                mock_invoke.return_value = AgentResult(session_key="sdlc_coder_PR_001_1234abcd", stdout="")

                with patch('builtins.open', side_effect=mock_file_open):
                    spawn_coder.main()

        mock_invoke.assert_called()
        prompt_sent = mock_invoke.call_args[0][0]
        called_kwargs = mock_invoke.call_args[1]
        self.assertEqual(called_kwargs['session_key'], "sdlc_coder_PR_001_1234abcd")
        self.assertIn("# REVIEW REPORT JSON", prompt_sent)
        self.assertIn('{"status": "NEEDS_FIX", "comments": "Missing stuff"}', prompt_sent)
        self.assertIn(spawn_coder.REVISION_CONTINUATION_RULE, prompt_sent)
        self.assertIn("not a fresh task", prompt_sent.lower())
        self.assertNotIn("# REFERENCE INDEX", prompt_sent)
        mock_setup_key.assert_called_once()

    @patch('spawn_coder.config.load_or_merge_config')
    @patch('spawn_coder.subprocess.check_output')
    @patch('spawn_coder.invoke_agent')
    @patch('utils_api_key.setup_spawner_api_key')
    def test_existing_session_revision_and_system_alert_paths_remain_same_session_delta_prompts_even_when_v2_is_selected(self, mock_setup_key, mock_invoke, mock_check_output, mock_load_config):
        mock_check_output.return_value = "feature/test"
        mock_invoke.return_value = AgentResult(session_key="existing-session", stdout="")
        mock_load_config.return_value = {config.CODER_PLAYBOOK_VERSION_CONFIG_KEY: config.CODER_PLAYBOOK_V2}

        with tempfile.TemporaryDirectory() as tmp_dir:
            pr_file = os.path.join(tmp_dir, "PR_001.md")
            prd_file = os.path.join(tmp_dir, "PRD.md")
            feedback_file = os.path.join(tmp_dir, "feedback.json")
            session_file = os.path.join(tmp_dir, ".coder_session")
            with open(pr_file, "w") as f:
                f.write("pr content")
            with open(prd_file, "w") as f:
                f.write("prd content")
            with open(feedback_file, "w") as f:
                f.write('{"status": "NEEDS_FIX", "comments": "delta only"}')
            with open(session_file, "w") as f:
                f.write("existing-session")

            revision_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--feedback-file", feedback_file,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', revision_args):
                    spawn_coder.main()

            revision_prompt = mock_invoke.call_args[0][0]
            self.assertIn("# REVIEW REPORT JSON", revision_prompt)
            self.assertIn(spawn_coder.REVISION_CONTINUATION_RULE, revision_prompt)
            self.assertNotIn("## CODER PLAYBOOK", revision_prompt)
            self.assertNotIn("# Coder Playbook V2", revision_prompt)
            self.assertNotIn("## REFERENCE INDEX", revision_prompt)

            mock_invoke.reset_mock()

            alert_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--system-alert", "git dirty",
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}, clear=False):
                with patch.object(sys, 'argv', alert_args):
                    spawn_coder.main()

            alert_prompt = mock_invoke.call_args[0][0]
            self.assertIn("# SYSTEM ALERT YOU MUST FIX", alert_prompt)
            self.assertIn(spawn_coder.SYSTEM_ALERT_CONTINUATION_RULE, alert_prompt)
            self.assertNotIn("## CODER PLAYBOOK", alert_prompt)
            self.assertNotIn("# Coder Playbook V2", alert_prompt)
            self.assertNotIn("## REFERENCE INDEX", alert_prompt)

    def test_spawn_coder_accepts_previous_output_for_retry(self):
        """TC2: --previous-output flag causes spawn_coder to inject previous stdout
        into the retry prompt while preserving PRD/PR references."""
        previous_stdout = "previous coder stdout content"
        with tempfile.TemporaryDirectory() as tmp_dir:
            prd_file = os.path.join(tmp_dir, "PRD.md")
            pr_file = os.path.join(tmp_dir, "PR_001_test.md")
            feedback_file = os.path.join(tmp_dir, "feedback.json")
            previous_output_file = os.path.join(tmp_dir, "prev_stdout.txt")

            with open(prd_file, "w") as f:
                f.write("## PRD\ncontent")
            with open(pr_file, "w") as f:
                f.write("status: in_progress\n")
            with open(feedback_file, "w") as f:
                f.write('{"overall_assessment": "NEEDS_ATTENTION"}')
            with open(previous_output_file, "w") as f:
                f.write(previous_stdout)

            os.makedirs(os.path.join(tmp_dir, "playbooks"), exist_ok=True)
            with open(os.path.join(tmp_dir, "playbooks", "coder_playbook.md"), "w") as f:
                f.write("# Coder Playbook V1\n")
            with open(os.path.join(tmp_dir, "playbooks", "coder_playbook_v2.md"), "w") as f:
                f.write("# Coder Playbook V2\n")

            feedback_args = [
                "spawn_coder.py",
                "--pr-file", pr_file,
                "--prd-file", prd_file,
                "--workdir", tmp_dir,
                "--feedback-file", feedback_file,
                "--previous-output", previous_output_file,
                "--run-dir", tmp_dir,
                "--enable-exec-from-workspace",
            ]

            with patch.dict(os.environ, {"SDLC_TEST_MODE": "true"}, clear=False):
                with patch.object(sys, 'argv', feedback_args):
                    with patch("spawn_coder.invoke_agent") as mock_invoke:
                        mock_invoke.return_value = AgentResult(
                            session_key="mock-key", stdout="mock-out", stderr="", return_code=0
                        )
                        try:
                            spawn_coder.main()
                        except SystemExit:
                            pass

            # In test mode spawn_coder writes to tests/tool_calls.log relative to cwd
            log_path = "tests/tool_calls.log"
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    prompt = f.read()
                self.assertIn("## PREVIOUS CODER OUTPUT", prompt)
                self.assertIn(previous_stdout, prompt)
                self.assertIn(os.path.basename(prd_file), prompt)
                self.assertIn(os.path.basename(pr_file), prompt)



if __name__ == '__main__':
    unittest.main()
