import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Force scripts into path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import orchestrator


def _init_git_repo(workdir: Path) -> None:
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(workdir), "init"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(workdir), "config", "user.name", "SDLC Test Sandbox"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(workdir), "config", "user.email", "sdlc-test-sandbox@example.invalid"],
        check=True,
        capture_output=True,
    )
    # Ignore logger temp directory to prevent false dirty-workspace triggers
    gitignore = workdir / ".gitignore"
    gitignore.write_text(".tmp/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workdir), "add", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(workdir), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )


class TestOrchestratorHandoffIntegration(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tempdirs: list[tempfile.TemporaryDirectory[str]] = []
        self._old_env = {
            "SDLC_BYPASS_BRANCH_CHECK": os.environ.get("SDLC_BYPASS_BRANCH_CHECK"),
            "SDLC_TEST_MODE": os.environ.get("SDLC_TEST_MODE"),
        }
        os.environ["SDLC_BYPASS_BRANCH_CHECK"] = "1"
        os.environ["SDLC_TEST_MODE"] = "true"
        self.orig_parse = orchestrator.parse_affected_projects
        orchestrator.parse_affected_projects = lambda _path: []
        self.orig_validate = orchestrator.validate_prd_is_committed
        orchestrator.validate_prd_is_committed = lambda _prd, _workdir: True

    def tearDown(self):
        os.chdir(self._orig_cwd)
        orchestrator.parse_affected_projects = self.orig_parse
        orchestrator.validate_prd_is_committed = self.orig_validate
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for tempdir in self._tempdirs:
            tempdir.cleanup()

    def _make_workspace(self, dirty: bool = False):
        tempdir = tempfile.TemporaryDirectory()
        self._tempdirs.append(tempdir)
        root = Path(tempdir.name)
        workdir = root / "workdir"
        global_dir = root / "global"
        prd_file = root / "dummy.md"

        global_dir.mkdir(parents=True, exist_ok=True)
        _init_git_repo(workdir)
        prd_file.write_text("# Dummy PRD\n", encoding="utf-8")

        if dirty:
            tracked_file = workdir / "tracked.txt"
            tracked_file.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(workdir), "add", "tracked.txt"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(workdir), "commit", "-m", "track file"], check=True, capture_output=True)
            tracked_file.write_text("dirty\n", encoding="utf-8")

        job_dir = global_dir / ".sdlc_runs" / workdir.name / prd_file.stem
        return workdir, global_dir, prd_file, job_dir

    def _make_args(self, workdir: Path, prd_file: Path, global_dir: Path, **overrides):
        values = {
            "workdir": str(workdir),
            "prd_file": str(prd_file),
            "max_prs_to_process": 50,
            "coder_session_strategy": "on-escalation",
            "force_replan": "false",
            "channel": "slack:C123",
            "global_dir": str(global_dir),
            "test_sleep": False,
            "enable_exec_from_workspace": True,
            "cleanup": False,
            "resume": False,
            "withdraw": False,
            "debug": False,
            "engine": "openclaw",
            "model": "test-model",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    @staticmethod
    def _printed_messages(mock_print) -> str:
        return "\n".join(" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list)

    def test_dirty_workspace(self):
        workdir, global_dir, prd_file, _job_dir = self._make_workspace(dirty=True)
        args = self._make_args(workdir, prd_file, global_dir)
        real_run = subprocess.run

        def run_side_effect(cmd, *a, **k):
            if isinstance(cmd, list) and any(str(part).endswith("doctor.py") for part in cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *a, **k)

        with patch("argparse.ArgumentParser.parse_args", return_value=args), \
             patch("subprocess.run", side_effect=run_side_effect), \
             patch("os.open", return_value=99), \
             patch("fcntl.flock"), \
             patch("builtins.print") as mock_print, \
             patch("orchestrator.notify_channel"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("git_utils.check_git_boundary"):
            with self.assertRaises(SystemExit) as exit_ctx:
                orchestrator.main()

        self.assertEqual(exit_ctx.exception.code, 1)
        self.assertIn("[FATAL] Dirty Git Workspace detected!", self._printed_messages(mock_print))

    def test_planner_failure(self):
        workdir, global_dir, prd_file, job_dir = self._make_workspace()
        args = self._make_args(workdir, prd_file, global_dir, force_replan="false")
        real_run = subprocess.run

        def run_side_effect(cmd, *a, **k):
            if isinstance(cmd, list) and any(str(part).endswith("doctor.py") for part in cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *a, **k)

        failed_planner = MagicMock()
        failed_planner.wait.return_value = None
        failed_planner.returncode = 1

        with patch("argparse.ArgumentParser.parse_args", return_value=args), \
             patch("subprocess.run", side_effect=run_side_effect), \
             patch("orchestrator.dpopen", return_value=failed_planner), \
             patch("os.open", return_value=99), \
             patch("fcntl.flock"), \
             patch("builtins.print") as mock_print, \
             patch("orchestrator.notify_channel"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("git_utils.check_git_boundary"):
            with self.assertRaises(SystemExit) as exit_ctx:
                orchestrator.main()

        self.assertEqual(exit_ctx.exception.code, 1)
        self.assertTrue(job_dir.exists(), "run-anchor job_dir should be created in a real temp workspace")
        self.assertTrue((job_dir / "baseline_commit.txt").exists())
        self.assertTrue((job_dir / "run_manifest.json").exists())
        self.assertIn("[FATAL] Planner failed", self._printed_messages(mock_print))

    def test_queue_empty(self):
        workdir, global_dir, prd_file, job_dir = self._make_workspace()
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "PR_001.md").write_text("status: closed\n", encoding="utf-8")
        args = self._make_args(
            workdir,
            prd_file,
            global_dir,
            force_replan="false",
            max_prs_to_process=0,
            coder_session_strategy="on-escalation",
        )
        real_run = subprocess.run

        def run_side_effect(cmd, *a, **k):
            if isinstance(cmd, list) and any(str(part).endswith("doctor.py") for part in cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if isinstance(cmd, list) and any(str(part).endswith("get_next_pr.py") for part in cmd):
                return subprocess.CompletedProcess(cmd, 0, stdout="[QUEUE_EMPTY]\n", stderr="")
            if isinstance(cmd, list) and any(str(part).endswith("spawn_verifier.py") for part in cmd):
                out_file = Path(cmd[cmd.index("--out-file") + 1])
                out_file.write_text(
                    json.dumps({"status": "NEEDS_FIX", "verification_details": []}),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return real_run(cmd, *a, **k)

        with patch("argparse.ArgumentParser.parse_args", return_value=args), \
             patch("subprocess.run", side_effect=run_side_effect), \
             patch("orchestrator.dpopen", side_effect=AssertionError("planner should not run in queue-empty test")), \
             patch("os.open", return_value=99), \
             patch("fcntl.flock"), \
             patch("builtins.print") as mock_print, \
             patch("orchestrator.notify_channel"), \
             patch("agent_driver.send_ignition_handshake"), \
             patch("git_utils.check_git_boundary"):
            with self.assertRaises(SystemExit) as exit_ctx:
                orchestrator.main()

        self.assertEqual(exit_ctx.exception.code, 1)
        self.assertTrue(job_dir.exists(), "run-anchor job_dir should be created in a real temp workspace")
        self.assertTrue((job_dir / "baseline_commit.txt").exists())
        self.assertTrue((job_dir / "run_manifest.json").exists())
        self.assertIn("[ACTION REQUIRED FOR MANAGER] UAT Failed", self._printed_messages(mock_print))


if __name__ == "__main__":
    unittest.main()
