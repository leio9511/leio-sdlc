"""Unit tests for case-1 engine eligibility and gate enforcement — PR-004."""
import os
import sys
import importlib
from unittest.mock import MagicMock, patch, ANY

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import config
from agent_driver import (
    AgentResult,
    is_case1_eligible,
    is_case1_strict_mode,
    invoke_agent_gated,
    invoke_agent,
    invoke_agent_two_phase,
    assert_no_heuristic_downgrade,
)


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════

def _reload_config():
    """Force re-import of config for env-var propagation."""
    importlib.reload(config)


def _set_continuity_mode(monkeypatch, mode: str):
    """Set SDLC_CONTINUITY_MODE and reload config."""
    monkeypatch.setenv("SDLC_CONTINUITY_MODE", mode)
    _reload_config()


# ══════════════════════════════════════════════════════════════════════════
# Test Cases 1-3: is_case1_eligible
# ══════════════════════════════════════════════════════════════════════════

class TestEngineEligibility:
    """TC 1-3: engine eligibility classification."""

    def test_openclaw_is_always_case1_eligible(self):
        """TC-1: is_case1_eligible('openclaw') returns True."""
        assert is_case1_eligible("openclaw") is True

    def test_unknown_engine_not_case1_eligible(self):
        """TC-2: is_case1_eligible('unknown_engine') returns False."""
        assert is_case1_eligible("unknown_engine") is False

    def test_gemini_not_presumed_eligible(self):
        """TC-3: is_case1_eligible('gemini') returns False — eligibility is determined by bootstrap result, not presumed."""
        assert is_case1_eligible("gemini") is False

    def test_empty_string_not_eligible(self):
        """Edge: empty string engine is not eligible."""
        assert is_case1_eligible("") is False

    def test_none_not_eligible(self):
        """Edge: None engine is not eligible."""
        assert is_case1_eligible(None) is False


# ══════════════════════════════════════════════════════════════════════════
# Test Cases 4-7: invoke_agent_gated dispatch
# ══════════════════════════════════════════════════════════════════════════

class TestInvokeAgentGated:
    """TC 4-7: mode-gated invoke dispatch routing."""

    def test_legacy_mode_delegates_to_invoke_agent(self, monkeypatch):
        """TC-4: in legacy mode, invoke_agent_gated calls invoke_agent regardless of engine."""
        _set_continuity_mode(monkeypatch, "legacy")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent", return_value=fake_result) as mock_invoke:
            result = invoke_agent_gated("test task", engine="gemini")

        mock_invoke.assert_called_once_with(
            "test task", session_key=None, role=None, run_dir=None, thinking=None
        )
        assert result is fake_result

    def test_case1_strict_mode_openclaw_delegates_to_invoke_agent(self, monkeypatch):
        """TC-5: in case1_strict mode with OpenClaw, invoke_agent_gated calls invoke_agent directly — no two-phase."""
        _set_continuity_mode(monkeypatch, "case1_strict")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent", return_value=fake_result) as mock_invoke:
            result = invoke_agent_gated("test task", engine="openclaw")

        mock_invoke.assert_called_once_with(
            "test task", session_key=None, role=None, run_dir=None, thinking=None
        )
        assert result is fake_result

    def test_case1_strict_mode_gemini_delegates_to_two_phase(self, monkeypatch):
        """TC-6: in case1_strict mode with Gemini, invoke_agent_gated calls invoke_agent_two_phase."""
        _set_continuity_mode(monkeypatch, "case1_strict")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent_two_phase", return_value=fake_result) as mock_tp:
            result = invoke_agent_gated("test task", engine="gemini")

        mock_tp.assert_called_once_with(
            "test task", session_key=None, role=None, run_dir=None, thinking=None
        )
        assert result is fake_result

    def test_case1_strict_mode_unknown_engine_rejected(self, monkeypatch):
        """TC-7: in case1_strict mode with unknown engine, returns error result with return_code=1."""
        _set_continuity_mode(monkeypatch, "case1_strict")

        result = invoke_agent_gated("test task", engine="unknown_engine")

        assert isinstance(result, AgentResult)
        assert result.return_code == 1
        assert result.stdout == ""

    def test_rejection_message_contains_exact_support_rule(self, monkeypatch):
        """TC-8: error stderr contains the exact text 'Only case-1 engines are in scope for strong continuity support.'"""
        _set_continuity_mode(monkeypatch, "case1_strict")

        result = invoke_agent_gated("test task", engine="unknown_engine")

        assert "Only case-1 engines are in scope for strong continuity support." in result.stderr

    def test_legacy_mode_unknown_engine_still_delegates_to_invoke_agent(self, monkeypatch):
        """Edge: in legacy mode, even an unknown engine delegates to invoke_agent (no gating)."""
        _set_continuity_mode(monkeypatch, "legacy")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent", return_value=fake_result) as mock_invoke:
            result = invoke_agent_gated("test task", engine="unknown_engine")

        mock_invoke.assert_called_once()
        assert result is fake_result


# ══════════════════════════════════════════════════════════════════════════
# Test Cases 9-10: heuristic downgrade guard
# ══════════════════════════════════════════════════════════════════════════

class TestHeuristicDowngradeGuard:
    """TC 9-10: assert_no_heuristic_downgrade."""

    def test_no_heuristic_downgrade_in_case1_strict(self):
        """TC-9: assert_no_heuristic_downgrade('case1_strict', True) raises RuntimeError."""
        with pytest.raises(RuntimeError) as exc_info:
            assert_no_heuristic_downgrade("case1_strict", True)
        assert "Heuristic downgrade" in str(exc_info.value)

    def test_heuristic_downgrade_allowed_in_legacy(self):
        """TC-10: assert_no_heuristic_downgrade('legacy', True) does NOT raise."""
        # Should not raise
        assert_no_heuristic_downgrade("legacy", True)

    def test_no_fallback_attempted_no_raise(self):
        """Edge: fallback_attempted=False does not raise even in case1_strict mode."""
        # Should not raise
        assert_no_heuristic_downgrade("case1_strict", False)

    def test_legacy_no_fallback_no_raise(self):
        """Edge: legacy mode with no fallback does not raise."""
        assert_no_heuristic_downgrade("legacy", False)


# ══════════════════════════════════════════════════════════════════════════
# Test Cases 11-12: OpenClaw regression protection
# ══════════════════════════════════════════════════════════════════════════

class TestOpenClawRegression:
    """TC 11-12: OpenClaw native path regression protection."""

    def test_openclaw_regression_legacy_mode(self, monkeypatch):
        """TC-11: OpenClaw engine in legacy mode produces identical result to invoke_agent()."""
        _set_continuity_mode(monkeypatch, "legacy")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent", return_value=fake_result) as mock_invoke:
            result = invoke_agent_gated("test task", engine="openclaw")

        mock_invoke.assert_called_once()
        assert result is fake_result

    def test_openclaw_regression_case1_strict_mode(self, monkeypatch):
        """TC-12: OpenClaw engine in case1_strict mode produces identical result to invoke_agent()."""
        _set_continuity_mode(monkeypatch, "case1_strict")

        fake_result = AgentResult(session_key="sess", stdout="ok", return_code=0)
        with patch("agent_driver.invoke_agent", return_value=fake_result) as mock_invoke:
            result = invoke_agent_gated("test task", engine="openclaw")

        mock_invoke.assert_called_once()
        assert result is fake_result

    def test_openclaw_no_two_phase_in_case1_strict(self, monkeypatch):
        """Edge: OpenClaw in case1_strict does NOT call invoke_agent_two_phase."""
        _set_continuity_mode(monkeypatch, "case1_strict")

        with patch("agent_driver.invoke_agent", return_value=AgentResult(session_key="s", stdout="ok")):
            with patch("agent_driver.invoke_agent_two_phase") as mock_tp:
                invoke_agent_gated("test task", engine="openclaw")
                mock_tp.assert_not_called()
