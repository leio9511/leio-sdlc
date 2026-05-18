import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import config
from runtime_launch_guard import (
    RuntimeInterpreterMismatch,
    is_authorized_runtime_launch,
    resolve_allowed_runtime_roots,
    resolve_expected_runtime_python,
    resolve_skill_root_for_runtime_smoke,
    runtime_python_for_skill_root,
    validate_runtime_interpreter,
)


def _canonicalize(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def test_expected_runtime_python_defaults_to_skill_root_venv_bin_python(tmp_path):
    skill_root = tmp_path / "portable-skill-root"
    scripts_dir = skill_root / "scripts"
    scripts_dir.mkdir(parents=True)
    script_path = scripts_dir / "runtime_launch_guard.py"
    script_path.write_text("# placeholder\n", encoding="utf-8")

    resolved = resolve_expected_runtime_python(script_path=str(script_path), env={})

    assert resolved == _canonicalize(skill_root / ".venv" / "bin" / "python")
    assert "/home/openclaw/projects/leio-sdlc" not in resolved
    assert "/.openclaw/skills/leio-sdlc" not in resolved


def test_runtime_python_for_skill_root_canonicalizes_controlled_runtime_interpreter(tmp_path):
    skill_root = tmp_path / "portable-skill-root"
    relative_skill_root = os.path.relpath(skill_root, start=Path.cwd())

    resolved = runtime_python_for_skill_root(relative_skill_root)

    assert resolved == _canonicalize(skill_root / ".venv" / "bin" / "python")
    assert resolved == resolve_expected_runtime_python(skill_root=relative_skill_root, env={})


def test_runtime_smoke_skill_root_resolver_derives_root_from_explicit_venv_python(tmp_path):
    skill_root = tmp_path / "skill-root"
    expected_python = skill_root / ".venv" / "bin" / "python"

    resolved = resolve_skill_root_for_runtime_smoke(expected_python=str(expected_python), env={})

    assert resolved == _canonicalize(skill_root)


def test_runtime_smoke_skill_root_resolver_derives_root_before_symlink_realpath_canonicalization(tmp_path):
    skill_root = tmp_path / "skill-root"
    expected_python = skill_root / ".venv" / "bin" / "python"
    base_python = tmp_path / "base" / "bin" / "python"
    expected_python.parent.mkdir(parents=True)
    base_python.parent.mkdir(parents=True)
    base_python.write_text("#!/bin/sh\n", encoding="utf-8")
    expected_python.symlink_to(base_python)

    resolved = resolve_skill_root_for_runtime_smoke(expected_python=str(expected_python), env={})

    assert os.path.realpath(expected_python) == _canonicalize(base_python)
    assert resolved == _canonicalize(skill_root)
    assert resolved != _canonicalize(base_python.parent.parent)


def test_runtime_smoke_skill_root_resolver_prefers_explicit_skill_root_over_python_shape(tmp_path):
    skill_root = tmp_path / "skill-root"
    explicit_root = tmp_path / "explicit-root"
    expected_python = skill_root / ".venv" / "bin" / "python"

    resolved = resolve_skill_root_for_runtime_smoke(
        skill_root=str(explicit_root),
        expected_python=str(expected_python),
        env={},
    )

    assert resolved == _canonicalize(explicit_root)


def test_runtime_interpreter_validation_accepts_canonical_matching_interpreter(tmp_path, monkeypatch):
    skill_root = tmp_path / "skill-root"
    python_path = skill_root / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("#!/bin/sh\n", encoding="utf-8")

    symlink_dir = tmp_path / "linked-bin"
    symlink_dir.mkdir()
    symlink_python = symlink_dir / "python"
    symlink_python.symlink_to(python_path)
    monkeypatch.chdir(symlink_dir)

    resolved = validate_runtime_interpreter(
        actual_python="./python",
        skill_root=str(skill_root),
        env={},
    )

    assert resolved == _canonicalize(python_path)


def test_runtime_interpreter_validation_rejects_system_or_other_python_with_clear_diagnostic(tmp_path):
    skill_root = tmp_path / "skill-root"
    expected_python = skill_root / ".venv" / "bin" / "python"
    expected_python.parent.mkdir(parents=True)
    expected_python.write_text("#!/bin/sh\n", encoding="utf-8")
    other_python = tmp_path / "other" / "bin" / "python3"
    other_python.parent.mkdir(parents=True)
    other_python.write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(RuntimeInterpreterMismatch) as excinfo:
        validate_runtime_interpreter(
            actual_python=str(other_python),
            expected_python=str(expected_python),
            env={},
        )

    diagnostic = str(excinfo.value)
    assert _canonicalize(other_python) in diagnostic
    assert _canonicalize(expected_python) in diagnostic
    assert "actual=" in diagnostic
    assert "expected=" in diagnostic
    assert (
        "deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap"
        in diagnostic
    )


def test_runtime_guard_does_not_hardcode_developer_workspace_or_prod_skill_path(tmp_path):
    guard_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "runtime_launch_guard.py")
    )
    with open(guard_path, encoding="utf-8") as handle:
        source = handle.read()

    assert "/home/openclaw/projects/leio-sdlc" not in source
    assert "~/.openclaw/skills/leio-sdlc" not in source

    skill_root = tmp_path / "arbitrary-root"
    script_path = skill_root / "scripts" / "runtime_launch_guard.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("# placeholder\n", encoding="utf-8")

    assert resolve_expected_runtime_python(script_path=str(script_path), env={}) == _canonicalize(
        skill_root / ".venv" / "bin" / "python"
    )


def test_resolve_allowed_runtime_roots_uses_built_in_compatibility_defaults_when_key_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    resolved = resolve_allowed_runtime_roots(app_config={})

    expected = [_canonicalize(path) for path in config.DEFAULT_ALLOWED_RUNTIME_ROOTS]
    assert resolved == expected


def test_resolve_allowed_runtime_roots_prefers_explicit_config_over_builtins(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    custom_root = "~/custom-runtime/skills"

    resolved = resolve_allowed_runtime_roots(
        app_config={config.ALLOWED_RUNTIME_ROOTS_CONFIG_KEY: [custom_root]}
    )

    assert resolved == [_canonicalize(custom_root)]
    assert _canonicalize("~/.openclaw/skills") not in resolved
    assert _canonicalize("~/.gemini/skills") not in resolved


def test_is_authorized_runtime_launch_accepts_true_descendant_and_rejects_false_prefix(tmp_path):
    allowed_root = tmp_path / ".gemini" / "skills"
    allowed_script = allowed_root / "leio-sdlc" / "scripts" / "orchestrator.py"
    false_prefix_script = tmp_path / ".gemini" / "skills-evil" / "leio-sdlc" / "scripts" / "orchestrator.py"

    assert is_authorized_runtime_launch(str(allowed_script), allowed_roots=[str(allowed_root)])
    assert not is_authorized_runtime_launch(str(false_prefix_script), allowed_roots=[str(allowed_root)])


def test_is_authorized_runtime_launch_uses_realpath_canonicalization(tmp_path):
    real_root = tmp_path / "real-runtime-root"
    real_script = real_root / "leio-sdlc" / "scripts" / "orchestrator.py"
    real_script.parent.mkdir(parents=True)
    real_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    symlink_root = tmp_path / "linked-runtime-root"
    symlink_root.symlink_to(real_root, target_is_directory=True)

    assert is_authorized_runtime_launch(str(real_script), allowed_roots=[str(symlink_root)])
