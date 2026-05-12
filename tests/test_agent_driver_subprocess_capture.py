import glob
import json
import os
import signal
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))

import agent_driver


class TestAgentDriverSubprocessCapture(unittest.TestCase):
    def _prepare_run_dir(self, session_key="capture-session", actual_id="existing-session"):
        run_dir = tempfile.TemporaryDirectory()
        temp_dir = os.path.join(run_dir.name, ".tmp")
        os.makedirs(temp_dir, exist_ok=True)
        session_map_path = os.path.join(temp_dir, f".session_map_{session_key}.json")
        with open(session_map_path, "w", encoding="utf-8") as handle:
            json.dump({"actual_id": actual_id}, handle)
        return run_dir, temp_dir

    def _write_helper_script(self, directory, name, body):
        script_path = os.path.join(directory, name)
        script = "#!/usr/bin/env python3\n" + body
        with open(script_path, "w", encoding="utf-8") as handle:
            handle.write(script)
        os.chmod(script_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return script_path

    def _capture_files(self, temp_dir):
        return sorted(
            glob.glob(os.path.join(temp_dir, "sdlc_stdout_*"))
            + glob.glob(os.path.join(temp_dir, "sdlc_stderr_*"))
        )

    def test_invoke_agent_returns_after_main_exit_when_descendant_keeps_inherited_output_fd_open(self):
        session_key = "descendant-session"
        run_dir, temp_dir = self._prepare_run_dir(session_key=session_key)
        pid_file = os.path.join(temp_dir, "descendant.pid")
        helper_path = self._write_helper_script(
            run_dir.name,
            "descendant_hang_helper.py",
            """
import os
import subprocess
import sys

pid_file = os.environ[\"DESCENDANT_PID_FILE\"]
descendant = subprocess.Popen([
    sys.executable,
    \"-c\",
    \"import time; time.sleep(30)\",
])
with open(pid_file, \"w\", encoding=\"utf-8\") as handle:
    handle.write(str(descendant.pid))

sys.stdout.write(\"main stdout\\n\")
sys.stdout.flush()
sys.stderr.write(\"main stderr\\n\")
sys.stderr.flush()
""",
        )

        try:
            with patch.dict(
                os.environ,
                {
                    "LLM_DRIVER": "gemini",
                    "DESCENDANT_PID_FILE": pid_file,
                },
                clear=False,
            ):
                with patch("agent_driver.resolve_cmd", return_value=helper_path):
                    started_at = time.monotonic()
                    result = agent_driver.invoke_agent(
                        "task",
                        session_key=session_key,
                        run_dir=run_dir.name,
                    )
                    elapsed = time.monotonic() - started_at

            self.assertLess(
                elapsed,
                5,
                f"invoke_agent should return promptly after main exit; took {elapsed:.2f}s",
            )
            self.assertEqual(result.stdout, "main stdout\n")
            self.assertEqual(result.stderr, "main stderr\n")
        finally:
            if os.path.exists(pid_file):
                with open(pid_file, "r", encoding="utf-8") as handle:
                    descendant_pid = int(handle.read().strip())
                try:
                    os.kill(descendant_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            run_dir.cleanup()

    def test_invoke_agent_reads_full_stdout_and_stderr_from_file_backed_capture(self):
        session_key = "output-session"
        run_dir, _temp_dir = self._prepare_run_dir(session_key=session_key)
        helper_path = self._write_helper_script(
            run_dir.name,
            "output_helper.py",
            """
import sys

sys.stdout.write(\"alpha\\nbeta\\n\")
sys.stdout.flush()
sys.stderr.write(\"gamma\\ndelta\\n\")
sys.stderr.flush()
""",
        )

        try:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value=helper_path):
                    result = agent_driver.invoke_agent(
                        "task",
                        session_key=session_key,
                        run_dir=run_dir.name,
                    )

            self.assertEqual(result.stdout, "alpha\nbeta\n")
            self.assertEqual(result.stderr, "gamma\ndelta\n")
            self.assertEqual(result.return_code, 0)
        finally:
            run_dir.cleanup()

    def test_invoke_agent_removes_capture_files_on_success_and_nonzero_exit(self):
        success_session = "cleanup-success"
        success_run_dir, success_temp_dir = self._prepare_run_dir(session_key=success_session)
        success_helper = self._write_helper_script(
            success_run_dir.name,
            "cleanup_success.py",
            """
import sys

sys.stdout.write(\"ok\\n\")
sys.stderr.write(\"warn\\n\")
sys.stdout.flush()
sys.stderr.flush()
""",
        )

        try:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value=success_helper):
                    result = agent_driver.invoke_agent(
                        "task",
                        session_key=success_session,
                        run_dir=success_run_dir.name,
                    )

            self.assertEqual(result.return_code, 0)
            self.assertEqual(self._capture_files(success_temp_dir), [])
        finally:
            success_run_dir.cleanup()

        failure_session = "cleanup-failure"
        failure_run_dir, failure_temp_dir = self._prepare_run_dir(session_key=failure_session)
        failure_helper = self._write_helper_script(
            failure_run_dir.name,
            "cleanup_failure.py",
            """
import sys

sys.stdout.write(\"bad stdout\\n\")
sys.stderr.write(\"bad stderr\\n\")
sys.stdout.flush()
sys.stderr.flush()
sys.exit(1)
""",
        )

        try:
            with patch.dict(os.environ, {"LLM_DRIVER": "gemini"}, clear=False):
                with patch("agent_driver.resolve_cmd", return_value=failure_helper):
                    with patch("agent_driver.time.sleep", return_value=None):
                        with self.assertRaises(SystemExit):
                            agent_driver.invoke_agent(
                                "task",
                                session_key=failure_session,
                                run_dir=failure_run_dir.name,
                            )

            self.assertEqual(self._capture_files(failure_temp_dir), [])
        finally:
            failure_run_dir.cleanup()

    def test_invoke_agent_retry_attempts_use_fresh_capture_files(self):
        session_key = "retry-session"
        run_dir, temp_dir = self._prepare_run_dir(session_key=session_key)
        attempt_state_path = os.path.join(temp_dir, "attempt_state.txt")
        audit_log_path = os.path.join(temp_dir, "capture_audit.jsonl")
        helper_path = self._write_helper_script(
            run_dir.name,
            "retry_helper.py",
            """
import json
import os
import sys

attempt_state_path = os.environ[\"ATTEMPT_STATE_PATH\"]
audit_log_path = os.environ[\"CAPTURE_AUDIT_PATH\"]

stdout_path = os.readlink(\"/proc/self/fd/1\")
stderr_path = os.readlink(\"/proc/self/fd/2\")
with open(audit_log_path, \"a\", encoding=\"utf-8\") as handle:
    handle.write(json.dumps({\"stdout\": stdout_path, \"stderr\": stderr_path}) + \"\\n\")

attempt = 0
if os.path.exists(attempt_state_path):
    with open(attempt_state_path, \"r\", encoding=\"utf-8\") as handle:
        attempt = int(handle.read().strip())
attempt += 1
with open(attempt_state_path, \"w\", encoding=\"utf-8\") as handle:
    handle.write(str(attempt))

if attempt == 1:
    sys.stdout.write(\"first attempt stdout\\n\")
    sys.stderr.write(\"first attempt stderr\\n\")
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(1)

sys.stdout.write(\"second attempt stdout\\n\")
sys.stderr.write(\"second attempt stderr\\n\")
sys.stdout.flush()
sys.stderr.flush()
""",
        )

        try:
            with patch.dict(
                os.environ,
                {
                    "LLM_DRIVER": "gemini",
                    "ATTEMPT_STATE_PATH": attempt_state_path,
                    "CAPTURE_AUDIT_PATH": audit_log_path,
                },
                clear=False,
            ):
                with patch("agent_driver.resolve_cmd", return_value=helper_path):
                    with patch("agent_driver.time.sleep", return_value=None):
                        result = agent_driver.invoke_agent(
                            "task",
                            session_key=session_key,
                            run_dir=run_dir.name,
                        )

            self.assertEqual(result.stdout, "second attempt stdout\n")
            self.assertEqual(result.stderr, "second attempt stderr\n")
            self.assertNotIn("first attempt", result.stdout)
            self.assertNotIn("first attempt", result.stderr)
            self.assertEqual(self._capture_files(temp_dir), [])

            with open(audit_log_path, "r", encoding="utf-8") as handle:
                capture_paths = [json.loads(line) for line in handle if line.strip()]

            self.assertEqual(len(capture_paths), 2)
            self.assertNotEqual(capture_paths[0]["stdout"], capture_paths[1]["stdout"])
            self.assertNotEqual(capture_paths[0]["stderr"], capture_paths[1]["stderr"])
        finally:
            run_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
