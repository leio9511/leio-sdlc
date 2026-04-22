import pytest
import sys
import os
import importlib

ENTRY_POINTS = {
    "orchestrator": ["--workdir", ".", "--prd-file", "dummy.md", "--channel", "stdout"],
    "spawn_coder": ["--pr-file", "dummy_pr.md", "--prd-file", "dummy_prd.md", "--workdir", "."],
    "spawn_reviewer": ["--workdir", "."], # Let's check required args for reviewer
    "spawn_verifier": ["--prd-files", "dummy.md", "--workdir", "."],
    "spawn_arbitrator": ["--pr-file", "dummy.md", "--diff-target", "HEAD", "--workdir", "."],
    "spawn_manager": ["--job-dir", ".", "--workdir", "."],
    "spawn_planner": ["--prd-file", "dummy.md", "--workdir", "."],
    "spawn_auditor": ["--prd-file", "dummy.md", "--workdir", ".", "--channel", "stdout"]
}

# reviewer args
# parser.add_argument("--pr-file", required=True, help="Path to the PR Contract file")
# parser.add_argument("--diff-target", required=True, help="Git diff target range (e.g., origin/master..HEAD)")
# parser.add_argument("--workdir", required=True, help="Working directory lock")

ENTRY_POINTS["spawn_reviewer"] = ["--pr-file", "dummy.md", "--diff-target", "HEAD", "--workdir", "."]

@pytest.mark.parametrize("script_module, req_args", ENTRY_POINTS.items())
def test_runtime_boundary_enforcement(script_module, req_args, monkeypatch, tmp_path, capsys):
    # Add scripts to path so we can import
    scripts_dir = os.path.abspath("scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    mock_runtime_dir = str(tmp_path / "mock_skills")
    monkeypatch.setenv("SDLC_RUNTIME_DIR", mock_runtime_dir)
    monkeypatch.delenv("SDLC_TEST_MODE", raising=False)
    
    # Reload config to pick up the mocked env var
    import config
    monkeypatch.setattr(config, "SDLC_RUNTIME_DIR", mock_runtime_dir)
    
    # Mock sys.argv
    invalid_script_path = "/invalid/path/script.py"
    monkeypatch.setattr(sys, "argv", [invalid_script_path] + req_args)
    
    module = importlib.import_module(script_module)
    importlib.reload(module)
    
    with pytest.raises(SystemExit) as e:
        module.main()
        
    assert e.value.code == 1
    
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert mock_runtime_dir in output, f"Hint should contain {mock_runtime_dir}, but output was: {output}"

