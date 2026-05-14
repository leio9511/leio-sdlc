import pytest
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
import spawn_reviewer
from agent_driver import AgentResult

def test_spawn_reviewer_uses_baseline_if_present():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        run_dir = os.path.join(td, "run_dir")
        os.makedirs(workdir)
        os.makedirs(run_dir)
        
        pr_file = os.path.join(td, "PR_003.md")
        with open(pr_file, "w") as f:
            f.write("dummy content")
            
        baseline_file = os.path.join(run_dir, "baseline_commit.txt")
        with open(baseline_file, "w") as f:
            f.write("mocked_baseline_hash_123")
            
        test_args = [
            "spawn_reviewer.py",
                "--enable-exec-from-workspace",
            "--pr-file", pr_file,
            "--diff-target", "master",
            "--workdir", workdir,
            "--run-dir", run_dir
        ]
        
        def fake_subprocess_run(cmd, *args, **kwargs):
            return MagicMock()
            
        def fake_exit(code):
            raise SystemExit(code)

        with patch("sys.argv", test_args), \
             patch("subprocess.run") as mock_run, \
             patch("spawn_reviewer.check_guardrails", return_value=None), \
             patch("spawn_reviewer.invoke_agent", return_value=AgentResult(session_key='...', stdout='{"status":"APPROVED"}', stderr='', return_code=0)), \
             patch("sys.exit", side_effect=fake_exit):
            
            try:
                spawn_reviewer.main()
            except SystemExit:
                pass
                
            calls = mock_run.call_args_list
            diff_cmd_found = False
            history_cmd_found = False
            for call in calls:
                cmd = call[0][0]
                if "git diff master --no-color >" in cmd:
                    diff_cmd_found = True
                if f"git log -p mocked_baseline_hash_123..HEAD > {os.path.join(run_dir, 'recent_history.diff')}" in cmd:
                    history_cmd_found = True
                    
            assert diff_cmd_found, "git diff command was not called correctly"
            assert history_cmd_found, "git log with baseline was not called correctly"

def test_spawn_reviewer_uses_fallback_if_missing():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        run_dir = os.path.join(td, "run_dir")
        os.makedirs(workdir)
        os.makedirs(run_dir)
        
        pr_file = os.path.join(td, "PR_003.md")
        with open(pr_file, "w") as f:
            f.write("dummy content")
            
        test_args = [
            "spawn_reviewer.py",
                "--enable-exec-from-workspace",
            "--pr-file", pr_file,
            "--diff-target", "master",
            "--workdir", workdir,
            "--run-dir", run_dir
        ]

        def fake_exit(code):
            raise SystemExit(code)

        with patch("sys.argv", test_args), \
             patch("subprocess.run") as mock_run, \
             patch("spawn_reviewer.check_guardrails", return_value=None), \
             patch("spawn_reviewer.invoke_agent", return_value=AgentResult(session_key='...', stdout='{"status":"APPROVED"}', stderr='', return_code=0)), \
             patch("sys.exit", side_effect=fake_exit):
            
            try:
                spawn_reviewer.main()
            except SystemExit:
                pass
                
            calls = mock_run.call_args_list
            history_cmd_found = False
            # history depth should be max(5, pr_num) -> max(5, 3) = 5
            expected_cmd = f"git log -n 5 -p master > {os.path.join(run_dir, 'recent_history.diff')}"
            for call in calls:
                cmd = call[0][0]
                if expected_cmd in cmd:
                    history_cmd_found = True
                    
            assert history_cmd_found, f"git log fallback command was not called correctly. Expected '{expected_cmd}' in calls"



def test_spawn_reviewer_creates_session_file():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        run_dir = os.path.join(td, "run_dir")
        os.makedirs(workdir)
        os.makedirs(run_dir)
        
        pr_file = os.path.join(td, "PR_003.md")
        with open(pr_file, "w") as f:
            f.write("dummy content")
            
        test_args = [
            "spawn_reviewer.py",
                "--enable-exec-from-workspace",
            "--pr-file", pr_file,
            "--diff-target", "master",
            "--workdir", workdir,
            "--run-dir", run_dir
        ]

        def fake_exit(code):
            raise SystemExit(code)

        with patch("sys.argv", test_args), \
             patch("subprocess.run"), \
             patch("spawn_reviewer.check_guardrails", return_value=None), \
             patch("spawn_reviewer.invoke_agent", return_value=AgentResult(session_key='subtask-123', stdout='{"status":"APPROVED"}', stderr='', return_code=0)), \
             patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}), \
             patch("sys.exit", side_effect=fake_exit):
            
            try:
                spawn_reviewer.main()
            except SystemExit:
                pass
                
            session_file = os.path.join(run_dir, ".reviewer_session")
            assert os.path.exists(session_file), "Session file was not created"
            with open(session_file, "r") as f:
                content = f.read().strip()
            assert content.startswith("subtask-")

def test_spawn_reviewer_system_alert():
    with tempfile.TemporaryDirectory() as td:
        workdir = os.path.join(td, "workdir")
        run_dir = os.path.join(td, "run_dir")
        os.makedirs(workdir)
        os.makedirs(run_dir)
        
        session_file = os.path.join(run_dir, ".reviewer_session")
        with open(session_file, "w") as f:
            f.write("subtask-12345678")
            
        test_args = [
            "spawn_reviewer.py",
                "--enable-exec-from-workspace",
            "--run-dir", run_dir,
            "--system-alert", "test alert"
        ]

        def fake_exit(code):
            raise SystemExit(code)

        with patch("sys.argv", test_args), \
             patch("spawn_reviewer.resolve_cmd", return_value="/usr/bin/openclaw"), \
             patch("subprocess.run") as mock_run, \
             patch("sys.exit", side_effect=fake_exit), \
             patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            
            try:
                spawn_reviewer.main()
            except SystemExit:
                pass
                
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[-5:] == ["agent", "--session-id", "subtask-12345678", "-m", "test alert"]
            assert "openclaw" in cmd[0]


def test_spawn_reviewer_system_alert_gemini():
    with tempfile.TemporaryDirectory() as td:
        run_dir = os.path.join(td, "run_dir")
        os.makedirs(run_dir)
        
        session_file = os.path.join(run_dir, ".reviewer_session")
        with open(session_file, "w") as f:
            f.write("subtask-12345678")
            
        test_args = [
            "spawn_reviewer.py",
                "--enable-exec-from-workspace",
            "--run-dir", run_dir,
            "--system-alert", "test alert"
        ]

        def fake_exit(code):
            raise SystemExit(code)

        with patch("sys.argv", test_args), \
             patch("spawn_reviewer.resolve_cmd", return_value="/usr/bin/gemini"), \
             patch("subprocess.run") as mock_run, \
             patch("sys.exit", side_effect=fake_exit), \
             patch.dict(os.environ, {"SDLC_TEST_MODE": "false"}):
            
            try:
                spawn_reviewer.main()
            except SystemExit:
                pass
                
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[-5:] == ["-r", "subtask-12345678", "-p", "test alert", "--yolo"]
            assert "gemini" in cmd[0]
