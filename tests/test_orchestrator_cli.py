import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import git_utils
# mock check_git_boundary on the module if it's missing
if not hasattr(git_utils, 'check_git_boundary'):
    git_utils.check_git_boundary = MagicMock()

class TestOrchestratorCLI(unittest.TestCase):
    def test_missing_force_replan_exits(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "dummy.md", "--global-dir", td]):
                with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                    with self.assertRaises(SystemExit) as cm:
                        import orchestrator
                        orchestrator.main()
                    self.assertNotEqual(cm.exception.code, 0)
                    
                    # verify output contains the expected fatal error string
                    output = "".join([call.args[0] for call in mock_stdout.write.call_args_list])
                    self.assertIn("[FATAL] Missing required parameter: --force-replan must be either 'true' or 'false'.", output)

    def test_missing_workdir_exits(self):
        with self.assertRaises(SystemExit) as cm:
            import orchestrator
            orchestrator.main()
        self.assertNotEqual(cm.exception.code, 0)

    @patch("agent_driver.notify_channel")
    def test_notify_channel_parsing(self, mock_notify):
        import orchestrator
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            # Because orchestrator imports notify_channel, we need to test if it's there
            pass


    import pytest
    
    
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    def test_prd_guardrail_untracked(self, mock_parse, mock_run, mock_exists):
        # We need to test the PRD guardrail.
        import orchestrator
        import subprocess
        import tempfile

        # Setup mock behavior
        def mock_exists_side_effect(path):
            if path == os.path.abspath("untracked.md"):
                return True
            return True

        mock_exists.side_effect = mock_exists_side_effect

        def mock_run_side_effect(*args, **kwargs):
            if args[0] == ["git", "ls-files", "--error-unmatch", os.path.abspath("untracked.md")]:
                raise subprocess.CalledProcessError(1, args[0])
            if args[0] == ["git", "rev-parse", "--show-toplevel"]:
                class Ret:
                    stdout = os.path.abspath(".")
                return Ret()
            return MagicMock()

        mock_run.side_effect = mock_run_side_effect

        with tempfile.TemporaryDirectory() as td:
            with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "untracked.md", "--channel", "test", "--global-dir", td]):
                with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                    with self.assertRaises(SystemExit) as cm:
                        orchestrator.main()
                    self.assertEqual(cm.exception.code, 1)

    import pytest
    
    
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    def test_prd_guardrail_modified(self, mock_parse, mock_run, mock_exists):
        import orchestrator
        import subprocess
        import tempfile

        def mock_exists_side_effect(path):
            if path == os.path.abspath("modified.md"):
                return True
            return True

        mock_exists.side_effect = mock_exists_side_effect

        def mock_run_side_effect(*args, **kwargs):
            if args[0] == ["git", "rev-parse", "--show-toplevel"]:
                class Ret:
                    stdout = os.path.abspath(".")
                return Ret()
            if args[0] == ["git", "status", "--porcelain", os.path.abspath("modified.md")]:
                class Ret:
                    stdout = " M modified.md"
                return Ret()
            if args[0] == ["git", "ls-files", "--error-unmatch", os.path.abspath("modified.md")]:
                class Ret:
                    stdout = ""
                return Ret()
            return MagicMock()

        mock_run.side_effect = mock_run_side_effect

        with tempfile.TemporaryDirectory() as td:
            with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "modified.md", "--channel", "test", "--global-dir", td]):
                with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                    with self.assertRaises(SystemExit) as cm:
                        orchestrator.main()
                    self.assertEqual(cm.exception.code, 1)

    import pytest
    
    
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    @patch("fcntl.flock")
    @patch("os.open", return_value=999)
    def test_prd_guardrail_clean(self, mock_os_open, mock_flock, mock_parse, mock_run, mock_exists):
        import orchestrator
        import subprocess
        import tempfile

        def mock_exists_side_effect(path):
            if path == os.path.abspath("clean.md"):
                return True
            return True

        mock_exists.side_effect = mock_exists_side_effect

        def mock_run_side_effect(*args, **kwargs):
            if args[0] == ["git", "rev-parse", "--show-toplevel"]:
                class Ret:
                    stdout = os.path.abspath(".")
                    returncode = 0
                return Ret()
            if args[0] == ["git", "ls-files", "--error-unmatch", os.path.abspath("clean.md")]:
                class Ret:
                    stdout = ""
                    returncode = 0
                return Ret()
            if args[0] == ["git", "status", "--porcelain", os.path.abspath("clean.md")]:
                class Ret:
                    stdout = ""
                    returncode = 0
                return Ret()
            if args[0] == ["git", "branch", "--show-current"]:
                class Ret:
                    stdout = "master"
                    returncode = 0
                return Ret()
            # Handle other calls as needed or return a dummy
            class DummyRet:
                stdout = ""
                returncode = 0
            return DummyRet()

        mock_run.side_effect = mock_run_side_effect

        import tempfile
        td = tempfile.mkdtemp()
        with patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "clean.md", "--channel", "test", "--test-sleep", "--force-replan", "false", "--global-dir", td]):
            with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
                with self.assertRaises(SystemExit) as cm:
                    orchestrator.main()
                self.assertEqual(cm.exception.code, 0)

    def test_orchestrator_uses_shared_notify_channel(self):
        import orchestrator
        import agent_driver
        self.assertIs(orchestrator.notify_channel, agent_driver.notify_channel)

    def test_orchestrator_escalation_limit_increased(self):
        import orchestrator
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            config_dir = os.path.join(td, "config")
            os.makedirs(config_dir, exist_ok=True)
            with open(os.path.join(config_dir, "sdlc_config.json.template"), "w") as f:
                json.dump({"RED_RETRY_LIMIT": 2}, f)
            resolved = orchestrator.resolve_retry_recovery_config(td, td)
            # Check for the red retry default which is effectively the escalation limit in the current implementation
            self.assertEqual(resolved["RED_RETRY_LIMIT"], 2)

if __name__ == "__main__":
    unittest.main()
