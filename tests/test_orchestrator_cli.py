import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import git_utils
# mock check_git_boundary on the module if it's missing
if not hasattr(git_utils, 'check_git_boundary'):
    git_utils.check_git_boundary = MagicMock()

class TestOrchestratorCLI(unittest.TestCase):
    @patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--prd-file", "dummy.md"])
    def test_missing_workdir_exits(self):
        with self.assertRaises(SystemExit) as cm:
            import orchestrator
            orchestrator.main()
        self.assertNotEqual(cm.exception.code, 0)

    @patch("subprocess.run")
    def test_notify_channel_parsing(self, mock_run):
        import orchestrator
        with patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            orchestrator.notify_channel("slack:channel:C12345", "Test message")
        mock_run.assert_called_with(["openclaw", "message", "send", "--channel", "slack", "-t", "channel:C12345", "-m", "🤖 [SDLC Engine] Test message"], check=False)

    @patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "untracked.md", "--channel", "test"])
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    def test_prd_guardrail_untracked(self, mock_parse, mock_run, mock_exists):
        # We need to test the PRD guardrail.
        import orchestrator
        import subprocess

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

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                orchestrator.main()
            self.assertEqual(cm.exception.code, 1)

    @patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "modified.md", "--channel", "test"])
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    def test_prd_guardrail_modified(self, mock_parse, mock_run, mock_exists):
        import orchestrator
        import subprocess

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

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                orchestrator.main()
            self.assertEqual(cm.exception.code, 1)

    @patch("sys.argv", ["orchestrator.py", "--enable-exec-from-workspace", "--workdir", ".", "--prd-file", "clean.md", "--channel", "test", "--test-sleep"])
    @patch("os.path.exists")
    @patch("subprocess.run")
    @patch("orchestrator.parse_affected_projects", return_value=[])
    def test_prd_guardrail_clean(self, mock_parse, mock_run, mock_exists):
        import orchestrator
        import subprocess

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

        with patch("sys.stdout", new_callable=MagicMock) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                orchestrator.main()
            self.assertEqual(cm.exception.code, 0)

if __name__ == "__main__":
    unittest.main()
