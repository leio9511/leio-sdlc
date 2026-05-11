import pytest
import sys
import os
import importlib

ENTRY_POINTS = {
    "orchestrator": ["--workdir", ".", "--prd-file", "dummy.md", "--channel", "stdout"],
    "spawn_coder": ["--pr-file", "dummy_pr.md", "--prd-file", "dummy_prd.md", "--workdir", "."],
    "spawn_reviewer": ["--pr-file", "dummy.md", "--diff-target", "HEAD", "--workdir", "."],
    "spawn_verifier": ["--prd-files", "dummy.md", "--workdir", "."],
    "spawn_arbitrator": ["--pr-file", "dummy.md", "--diff-target", "HEAD", "--workdir", "."],
    "spawn_manager": ["--job-dir", ".", "--workdir", "."],
    "spawn_planner": ["--prd-file", "dummy.md", "--workdir", "."],
    "spawn_auditor": ["--prd-file", "dummy.md", "--workdir", ".", "--channel", "stdout"],
}


def _canonicalize(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


@pytest.mark.parametrize("script_module, req_args", ENTRY_POINTS.items())
def test_runtime_boundary_enforcement(script_module, req_args, monkeypatch, tmp_path, capsys):
    scripts_dir = os.path.abspath("scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    mock_allowed_root = tmp_path / "allowed-runtime" / "skills"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SDLC_TEST_MODE", raising=False)

    import config

    monkeypatch.setattr(
        config,
        "DEFAULT_ALLOWED_RUNTIME_ROOTS",
        [str(mock_allowed_root)],
    )
    monkeypatch.setattr(config, "SDLC_RUNTIME_DIR", str(mock_allowed_root))

    invalid_script_path = str(tmp_path / "workspace" / "script.py")
    monkeypatch.setattr(sys, "argv", [invalid_script_path] + req_args)

    module = importlib.import_module(script_module)
    importlib.reload(module)

    with pytest.raises(SystemExit) as e:
        module.main()

    assert e.value.code == 1

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert str(mock_allowed_root) in output, f"Hint should contain {mock_allowed_root}, but output was: {output}"


def test_runtime_boundary_enforcement_rejects_false_prefix_path(monkeypatch, tmp_path, capsys):
    scripts_dir = os.path.abspath("scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    allowed_root = tmp_path / ".gemini" / "skills"
    false_prefix_script = tmp_path / ".gemini" / "skills-evil" / "leio-sdlc" / "scripts" / "spawn_auditor.py"

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SDLC_TEST_MODE", raising=False)

    import config

    monkeypatch.setattr(config, "DEFAULT_ALLOWED_RUNTIME_ROOTS", [str(allowed_root)])
    monkeypatch.setattr(config, "SDLC_RUNTIME_DIR", str(allowed_root))
    monkeypatch.setattr(
        sys,
        "argv",
        [str(false_prefix_script), "--prd-file", "dummy.md", "--workdir", ".", "--channel", "stdout"],
    )

    import spawn_auditor

    importlib.reload(spawn_auditor)

    with pytest.raises(SystemExit) as e:
        spawn_auditor.main()

    assert e.value.code == 1
    output = capsys.readouterr().out
    assert str(_canonicalize(str(allowed_root))) in output

