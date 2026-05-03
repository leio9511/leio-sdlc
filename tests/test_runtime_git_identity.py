import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import runtime_git_identity


def test_build_runtime_git_config_requires_explicit_role():
    with pytest.raises(ValueError):
        runtime_git_identity.build_runtime_git_config(None)

    with pytest.raises(ValueError):
        runtime_git_identity.build_runtime_git_config("")

    with pytest.raises(ValueError):
        runtime_git_identity.build_runtime_git_config("   ")

    assert runtime_git_identity.build_runtime_git_config("coder") == [
        "-c",
        "sdlc.runtime=1",
        "-c",
        "sdlc.role=coder",
    ]


def test_runtime_git_wrapper_injects_runtime_and_role_config(tmp_path):
    script = Path(__file__).parent.parent / "scripts" / "runtime_git_identity.py"
    result = subprocess.run(
        [sys.executable, str(script), "--role", "merge_code", "--print-command", "--", "merge", "feature/test"],
        capture_output=True,
        text=True,
        check=True,
    )

    output = result.stdout.strip()
    assert output.startswith("git ")
    assert "-c sdlc.runtime=1" in output
    assert "-c sdlc.role=merge_code" in output
    assert output.endswith("merge feature/test")
