import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import config
from runtime_launch_guard import is_authorized_runtime_launch, resolve_allowed_runtime_roots


def _canonicalize(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


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
