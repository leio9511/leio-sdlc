"""Unit tests for continuity mode flag lifecycle — PR-001."""
import os
import sys
import pytest

# Ensure scripts/ is on the path for config and agent_driver imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))

import config


class TestContinuityMode:
    """Test suite for SDLC_CONTINUITY_MODE flag, get_continuity_mode, and observer."""

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _reload_config():
        """Force re-import of config so env-var changes take effect."""
        import importlib
        importlib.reload(config)

    # ── Test Cases ───────────────────────────────────────────────────────

    def test_default_continuity_mode_is_legacy(self, monkeypatch):
        """TC-1: get_continuity_mode() returns 'legacy' when no env var is set."""
        monkeypatch.delenv("SDLC_CONTINUITY_MODE", raising=False)
        self._reload_config()
        assert config.get_continuity_mode() == "legacy"

    def test_env_var_sets_case1_strict(self, monkeypatch):
        """TC-2: get_continuity_mode() returns 'case1_strict' when SDLC_CONTINUITY_MODE=case1_strict."""
        monkeypatch.setenv("SDLC_CONTINUITY_MODE", "case1_strict")
        self._reload_config()
        assert config.get_continuity_mode() == "case1_strict"

    def test_env_var_sets_legacy_explicitly(self, monkeypatch):
        """TC-3: get_continuity_mode() returns 'legacy' when SDLC_CONTINUITY_MODE=legacy."""
        monkeypatch.setenv("SDLC_CONTINUITY_MODE", "legacy")
        self._reload_config()
        assert config.get_continuity_mode() == "legacy"

    def test_invalid_mode_raises_value_error(self, monkeypatch):
        """TC-4: get_continuity_mode() raises ValueError when mode is unrecognized."""
        monkeypatch.setenv("SDLC_CONTINUITY_MODE", "invalid_mode")
        self._reload_config()
        with pytest.raises(ValueError) as exc_info:
            config.get_continuity_mode()
        assert "invalid_mode" in str(exc_info.value)

    def test_case1_strict_observer_returns_true(self, monkeypatch):
        """TC-5: is_case1_strict_mode() returns True when mode is 'case1_strict'."""
        from agent_driver import is_case1_strict_mode
        monkeypatch.setenv("SDLC_CONTINUITY_MODE", "case1_strict")
        self._reload_config()
        assert is_case1_strict_mode() is True

    def test_case1_strict_observer_returns_false_for_legacy(self, monkeypatch):
        """TC-6: is_case1_strict_mode() returns False when mode is 'legacy'."""
        from agent_driver import is_case1_strict_mode
        monkeypatch.setenv("SDLC_CONTINUITY_MODE", "legacy")
        self._reload_config()
        assert is_case1_strict_mode() is False

    def test_config_template_contains_continuity_mode_key(self):
        """TC-7: config/sdlc_config.json.template includes 'continuity_mode' key with default 'legacy'."""
        import json
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            "sdlc_config.json.template",
        )
        with open(template_path, "r") as f:
            template = json.load(f)
        assert "continuity_mode" in template
        assert template["continuity_mode"] == "legacy"
