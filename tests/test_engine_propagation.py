import os
import sys
import tempfile
import pytest
from unittest.mock import patch

# Add scripts directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

def test_spawn_planner_engine_propagation():
    import spawn_planner
    
    with tempfile.TemporaryDirectory() as tmpdir:
        prd_file = os.path.join(tmpdir, "PRD_Test.md")
        with open(prd_file, "w") as f:
            f.write("# Mock PRD\n")
            
        test_args = [
            "spawn_planner.py",
            "--prd-file", prd_file,
            "--workdir", tmpdir,
            "--run-dir", tmpdir,
            "--enable-exec-from-workspace"
        ]
        
        # Case 1: LLM_DRIVER is set to 'gemini', --engine is not passed.
        # Expected: engine resolves to 'gemini', LLM_DRIVER remains 'gemini'.
        env = os.environ.copy()
        env["LLM_DRIVER"] = "gemini"
        env["SDLC_TEST_MODE"] = "true"
        
        with patch("sys.argv", test_args), patch.dict(os.environ, env, clear=True):
            # We need to ensure some env vars from parent are kept if needed, 
            # but patch.dict with clear=True might be too aggressive.
            # Actually, spawn_planner needs some env vars like PATH maybe?
            # Let's not use clear=True, just patch the dict.
            pass
            
        with patch("sys.argv", test_args), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
            try:
                spawn_planner.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "gemini"

        # Case 2: LLM_DRIVER is set to 'gemini', --engine is passed as 'openclaw'.
        # Expected: engine resolves to 'openclaw', LLM_DRIVER becomes 'openclaw'.
        with patch("sys.argv", test_args + ["--engine", "openclaw"]), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
            try:
                spawn_planner.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "openclaw"

        # Case 3: LLM_DRIVER is not set, --engine is not passed.
        # Expected: engine resolves to default_engine (openclaw), LLM_DRIVER becomes default_engine (openclaw).
        # We must ensure LLM_DRIVER is NOT in env.
        with patch("sys.argv", test_args), patch.dict(os.environ, {"SDLC_TEST_MODE": "true"}):
            if "LLM_DRIVER" in os.environ:
                del os.environ["LLM_DRIVER"]
            try:
                spawn_planner.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "openclaw"


def test_spawn_coder_engine_propagation():
    import spawn_coder
    
    with tempfile.TemporaryDirectory() as tmpdir:
        prd_file = os.path.join(tmpdir, "PRD_Test.md")
        with open(prd_file, "w") as f:
            f.write("# Mock PRD\n")
        pr_file = os.path.join(tmpdir, "PR_001_Test.md")
        with open(pr_file, "w") as f:
            f.write("pr content")
            
        test_args = [
            "spawn_coder.py",
            "--prd-file", prd_file,
            "--pr-file", pr_file,
            "--workdir", tmpdir,
            "--run-dir", tmpdir,
            "--enable-exec-from-workspace"
        ]
        
        # Mock git branch check to avoid fatal error
        with patch("spawn_coder.subprocess.check_output", return_value="feature/test"):
            # Case 1: LLM_DRIVER is set to 'gemini', --engine is not passed.
            with patch("sys.argv", test_args), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
                try:
                    spawn_coder.main()
                except SystemExit as e:
                    assert e.code == 0
                assert os.environ.get("LLM_DRIVER") == "gemini"

            # Case 2: LLM_DRIVER is set to 'gemini', --engine is passed as 'openclaw'.
            with patch("sys.argv", test_args + ["--engine", "openclaw"]), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
                try:
                    spawn_coder.main()
                except SystemExit as e:
                    assert e.code == 0
                assert os.environ.get("LLM_DRIVER") == "openclaw"

            # Case 3: LLM_DRIVER is not set, --engine is not passed.
            with patch("sys.argv", test_args), patch.dict(os.environ, {"SDLC_TEST_MODE": "true"}):
                if "LLM_DRIVER" in os.environ:
                    del os.environ["LLM_DRIVER"]
                try:
                    spawn_coder.main()
                except SystemExit as e:
                    assert e.code == 0
                assert os.environ.get("LLM_DRIVER") == "openclaw"


def test_spawn_reviewer_engine_propagation():
    import spawn_reviewer
    
    with tempfile.TemporaryDirectory() as tmpdir:
        pr_file = os.path.join(tmpdir, "PR_002_dummy.md")
        with open(pr_file, "w") as f:
            f.write("Dummy PR Content")
        diff_file = os.path.join(tmpdir, "dummy.diff")
        with open(diff_file, "w") as f:
            f.write("+++ b/dummy.py")
            
        test_args = [
            "spawn_reviewer.py",
            "--pr-file", pr_file,
            "--diff-target", "HEAD",
            "--override-diff-file", diff_file,
            "--workdir", tmpdir,
            "--run-dir", tmpdir,
            "--enable-exec-from-workspace"
        ]
        
        # Case 1: LLM_DRIVER is set to 'gemini', --engine is not passed.
        with patch("sys.argv", test_args), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
            try:
                spawn_reviewer.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "gemini"

        # Case 2: LLM_DRIVER is set to 'gemini', --engine is passed as 'openclaw'.
        with patch("sys.argv", test_args + ["--engine", "openclaw"]), patch.dict(os.environ, {"LLM_DRIVER": "gemini", "SDLC_TEST_MODE": "true"}):
            try:
                spawn_reviewer.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "openclaw"

        # Case 3: LLM_DRIVER is not set, --engine is not passed.
        with patch("sys.argv", test_args), patch.dict(os.environ, {"SDLC_TEST_MODE": "true"}):
            if "LLM_DRIVER" in os.environ:
                del os.environ["LLM_DRIVER"]
            try:
                spawn_reviewer.main()
            except SystemExit as e:
                assert e.code == 0
            assert os.environ.get("LLM_DRIVER") == "openclaw"
