"""
Canonical shared resolver for OpenClaw thinking-level normalization.

This module is the single source of truth for:
- The default thinking value ("high")
- The allowed thinking values ({low, medium, high, xhigh})
- Validation and resolution of thinking-level inputs

No other module may define its own thinking default or allowed set.
All entrypoints and agent_driver MUST use resolve_thinking().
"""

# Allowed thinking values (exhaustive, closed set)
ALLOWED_THINKING_VALUES = frozenset({"low", "medium", "high", "xhigh"})

# Canonical default — the ONLY place this default is defined
DEFAULT_THINKING = "high"


def resolve_thinking(value: str | None) -> str:
    """
    Resolve and validate a thinking-level value.

    - If value is None or empty, return DEFAULT_THINKING ("high").
    - If value is in ALLOWED_THINKING_VALUES, return it unchanged.
    - If value is not in ALLOWED_THINKING_VALUES, raise ValueError
      with a message that includes the rejected value and the allowed set.

    This is the ONLY function allowed to apply the default or validate
    the allowed set. All entrypoints and agent_driver MUST use this
    function — no other module may define its own thinking default.
    """
    if value is None or value == "":
        return DEFAULT_THINKING

    if value in ALLOWED_THINKING_VALUES:
        return value

    raise ValueError(
        f"Invalid thinking level '{value}'. "
        f"Allowed values: {sorted(ALLOWED_THINKING_VALUES)}"
    )
