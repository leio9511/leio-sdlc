"""Unit tests for scripts/thinking_resolver.py — the canonical thinking-level resolver."""

import pytest
from scripts.thinking_resolver import (
    ALLOWED_THINKING_VALUES,
    DEFAULT_THINKING,
    resolve_thinking,
)


class TestResolveThinkingDefault:
    """Validates the canonical default behavior."""

    def test_resolve_default_when_none(self):
        """Given resolve_thinking(None), expect return value 'high'."""
        assert resolve_thinking(None) == "high"

    def test_resolve_default_when_empty_string(self):
        """Given resolve_thinking(''), expect return value 'high'."""
        assert resolve_thinking("") == "high"


class TestResolveThinkingExplicit:
    """Validates that explicit allowed values pass through unchanged."""

    def test_resolve_explicit_low(self):
        assert resolve_thinking("low") == "low"

    def test_resolve_explicit_medium(self):
        assert resolve_thinking("medium") == "medium"

    def test_resolve_explicit_high(self):
        assert resolve_thinking("high") == "high"

    def test_resolve_explicit_xhigh(self):
        assert resolve_thinking("xhigh") == "xhigh"


class TestResolveThinkingReject:
    """Validates that illegal values raise ValueError."""

    def test_reject_illegal_value(self):
        """Given resolve_thinking('invalid'), expect ValueError with rejected value and allowed set."""
        with pytest.raises(ValueError) as exc_info:
            resolve_thinking("invalid")
        message = str(exc_info.value)
        assert "invalid" in message
        assert "low" in message
        assert "medium" in message
        assert "high" in message
        assert "xhigh" in message

    def test_reject_random_string(self):
        """Given resolve_thinking('whatever'), expect ValueError."""
        with pytest.raises(ValueError):
            resolve_thinking("whatever")


class TestConstants:
    """Validates that constants are exactly as specified."""

    def test_allowed_set_is_exact(self):
        """Verify ALLOWED_THINKING_VALUES and DEFAULT_THINKING are canonical."""
        assert ALLOWED_THINKING_VALUES == frozenset({"low", "medium", "high", "xhigh"})
        assert DEFAULT_THINKING == "high"
