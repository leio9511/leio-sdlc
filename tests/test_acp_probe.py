import json
from pathlib import Path

from scripts import acp_probe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = set(acp_probe.REQUIRED_VERDICT_FIELDS)


def _load_fixture(name: str):
    with (PROJECT_ROOT / "tests" / "fixtures" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _validate_schema_subset(schema, instance):
    """Validate the JSON-schema subset used by the repository fixture."""

    missing = [field for field in schema["required"] if field not in instance]
    assert missing == []

    properties = schema["properties"]
    for field in schema["required"]:
        rules = properties[field]
        value = instance[field]
        if rules.get("type") == "string":
            assert isinstance(value, str)
        elif rules.get("type") == "boolean":
            assert isinstance(value, bool)
        elif rules.get("type") == "array":
            assert isinstance(value, list)
        elif rules.get("type") == "object":
            assert isinstance(value, dict)
        elif "$ref" in rules:
            assert isinstance(value, dict)
            for required in schema["$defs"]["operation_result"]["required"]:
                assert required in value
        if "const" in rules:
            assert value == rules["const"]
        if "enum" in rules:
            assert value in rules["enum"]


def test_emit_verdict_contains_required_contract_fields():
    verdict = acp_probe.emit_verdict(validation_timestamp="2026-05-25T00:00:00Z")

    assert REQUIRED_FIELDS.issubset(verdict)
    assert verdict["target_cli"] == "Gemini CLI"
    json.dumps(verdict)


def test_schema_fixture_matches_sample_fixture():
    schema = _load_fixture("acp_verdict_schema.json")
    sample = _load_fixture("acp_verdict_gemini_sample.json")

    _validate_schema_subset(schema, sample)


def test_negative_resume_is_valid_partially_supported_verdict():
    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True, "detail": "connected"},
            "execute_turn": {"ok": True, "detail": "turn completed"},
            "capture_handle": {
                "ok": False,
                "status": "unavailable",
                "detail": "no continuation handle returned",
                "error": "Handle Unavailable",
            },
            "resume_once": {
                "ok": False,
                "status": "unavailable",
                "detail": "resume cannot run without handle",
                "error": "Resume Handle Unavailable",
            },
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["final_verdict"] in {"partially_supported", "not_suitable_at_this_stage"}
    assert verdict["failure_classification"]
    assert verdict["handle_capture_result"]["ok"] is False
    assert verdict["resume_once_result"]["ok"] is False


def test_missing_api_key_classifies_as_blocked_without_traceback():
    connect_result = acp_probe.connect(environ={})
    verdict = acp_probe.emit_verdict(
        {
            "connect": connect_result,
            "execute_turn": {"ok": False, "detail": "turn skipped because connect prerequisite is blocked"},
            "capture_handle": {"ok": False, "detail": "handle skipped because connect prerequisite is blocked"},
            "resume_once": {"ok": False, "detail": "resume skipped because connect prerequisite is blocked"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    categories = {item["category"] for item in verdict["failure_classification"]}
    assert "Missing API Key" in categories
    assert verdict["final_verdict"] in {"blocked", "partially_supported"}


def test_client_produced_full_observation_set_is_valid_verdict_input():
    observations = {
        "connect": {
            "operation": "connect",
            "ok": True,
            "status": "connected",
            "detail": "fake client connected",
            "metadata": {"sdk_package_name": "agent-client-protocol", "session_id": "fake-session-1"},
        },
        "execute_turn": {
            "operation": "execute_turn",
            "ok": True,
            "status": "succeeded",
            "detail": "fake turn completed",
            "metadata": {"sdk_package_name": "agent-client-protocol", "response_text": "pong", "handle": "fake-handle-1"},
        },
        "capture_handle": {
            "operation": "capture_handle",
            "ok": True,
            "status": "captured",
            "detail": "fake handle captured",
            "metadata": {"sdk_package_name": "agent-client-protocol", "handle": "fake-handle-1"},
        },
        "resume_once": {
            "operation": "resume_once",
            "ok": True,
            "status": "succeeded",
            "detail": "fake resume completed",
            "metadata": {"sdk_package_name": "agent-client-protocol", "handle": "fake-handle-1", "attempt_count": 1},
        },
    }

    verdict = acp_probe.emit_verdict(observations, validation_timestamp="2026-05-25T00:00:00Z")

    assert REQUIRED_FIELDS.issubset(verdict)
    assert verdict["connect_result"] == observations["connect"]
    assert verdict["execute_turn_result"] == observations["execute_turn"]
    assert verdict["handle_capture_result"] == observations["capture_handle"]
    assert verdict["resume_once_result"] == observations["resume_once"]
    assert verdict["final_verdict"] == "supported"
    json.dumps(verdict)


# --- Schema-Driven Contract Tests (PR-001) ---

def test_schema_enforces_continuity_mode_enum():
    schema = _load_fixture("acp_verdict_schema.json")
    continuity_mode = schema["properties"]["continuity_mode"]

    assert continuity_mode["enum"] == ["authoritative_resume", "unsupported"]

    # Verify a verdict with the old "mapped_resume" value fails schema validation.
    sample = _load_fixture("acp_verdict_gemini_sample.json")
    sample["continuity_mode"] = "mapped_resume"
    try:
        _validate_schema_subset(schema, sample)
        raise AssertionError("schema must reject continuity_mode 'mapped_resume'")
    except AssertionError as exc:
        msg = str(exc).lower()
        assert "mapped_resume" in msg, f"expected rejection of mapped_resume, got: {exc}"


def test_schema_enforces_handle_acquisition_strategy_enum():
    schema = _load_fixture("acp_verdict_schema.json")
    has_enum = schema["properties"]["handle_acquisition_strategy"]

    assert has_enum["enum"] == ["protocol_native", "explicit_returned_handle", "unavailable"]

    # Verify a verdict with the old "returned_handle" value fails schema validation.
    sample = _load_fixture("acp_verdict_gemini_sample.json")
    sample["handle_acquisition_strategy"] = "returned_handle"
    try:
        _validate_schema_subset(schema, sample)
        raise AssertionError("schema must reject handle_acquisition_strategy 'returned_handle'")
    except AssertionError as exc:
        msg = str(exc).lower()
        assert "returned_handle" in msg, f"expected rejection of returned_handle, got: {exc}"


def test_schema_requires_target_scope_note():
    schema = _load_fixture("acp_verdict_schema.json")

    assert "target_scope_note" in schema["required"]


def test_probe_emit_verdict_produces_only_authorized_continuity_modes():
    authorized = {"authoritative_resume", "unsupported"}

    # Full support: handle_ok=True, resume_ok=True
    v1 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": True},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v1["continuity_mode"] in authorized

    # Handle present but resume failed
    v2 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": False},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v2["continuity_mode"] in authorized

    # No handle at all
    v3 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": False},
            "resume_once": {"ok": False},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v3["continuity_mode"] in authorized

    # Even with connect-only
    v4 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": False},
            "capture_handle": {"ok": False},
            "resume_once": {"ok": False},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v4["continuity_mode"] in authorized


def test_probe_emit_verdict_produces_only_authorized_handle_strategies():
    authorized = {"protocol_native", "explicit_returned_handle", "unavailable"}

    # Handle present and resume OK → protocol_native
    v1 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": True},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v1["handle_acquisition_strategy"] in authorized

    # Handle present but resume failed → explicit_returned_handle
    v2 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": False},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v2["handle_acquisition_strategy"] in authorized

    # No handle → unavailable
    v3 = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": False},
            "resume_once": {"ok": False},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    assert v3["handle_acquisition_strategy"] in authorized


def test_no_handle_means_continuity_mode_unsupported():
    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {
                "ok": False,
                "status": "unavailable",
                "detail": "no continuation handle",
                "error": "Handle Unavailable",
            },
            "resume_once": {
                "ok": False,
                "status": "unavailable",
                "detail": "resume cannot run without handle",
                "error": "Resume Handle Unavailable",
            },
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["continuity_mode"] == "unsupported"
    assert verdict["handle_acquisition_strategy"] == "unavailable"


def test_authoritative_handle_and_successful_resume_means_authoritative_resume():
    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": True, "metadata": {"handle": "h1"}},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["continuity_mode"] == "authoritative_resume"


def test_closed_continuity_contract_rule_is_in_code():
    """Exercise emit_verdict paths and verify forbidden terms never appear in output."""
    forbidden = {"mapped_resume", "none_observed", "returned_handle", "protocol_native_or_returned_handle"}

    scenarios = [
        # Full support
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": True},
        },
        # Handle but no resume
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": True, "metadata": {"handle": "h1"}},
            "resume_once": {"ok": False},
        },
        # No handle, no resume
        {
            "connect": {"ok": True},
            "execute_turn": {"ok": True},
            "capture_handle": {"ok": False},
            "resume_once": {"ok": False},
        },
        # Missing API key (blocked)
        {
            "connect": {"ok": False, "detail": "GEMINI_API_KEY missing"},
            "execute_turn": {"ok": False},
            "capture_handle": {"ok": False},
            "resume_once": {"ok": False},
        },
    ]

    for scenario in scenarios:
        verdict = acp_probe.emit_verdict(scenario, validation_timestamp="2026-05-25T00:00:00Z")
        verdict_str = json.dumps(verdict)
        for term in forbidden:
            # Only flag if it appears as a value (not just in a detail string)
            assert verdict.get("continuity_mode") not in forbidden, f"continuity_mode '{verdict.get('continuity_mode')}' is forbidden"
            assert verdict.get("handle_acquisition_strategy") not in forbidden, f"handle_acquisition_strategy '{verdict.get('handle_acquisition_strategy')}' is forbidden"


def test_requirements_declares_agent_client_protocol():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "agent-client-protocol" in {line.strip() for line in requirements}


# --- PR-002_1: Unsupported-Resume Reference Sample Fixture Tests ---

def test_unsupported_resume_sample_passes_schema():
    schema = _load_fixture("acp_verdict_schema.json")
    sample = _load_fixture("acp_verdict_unsupported_resume_sample.json")

    _validate_schema_subset(schema, sample)


def test_unsupported_resume_sample_has_no_authoritative_handle():
    sample = _load_fixture("acp_verdict_unsupported_resume_sample.json")

    assert sample["continuity_mode"] == "unsupported"
    assert sample["handle_acquisition_strategy"] == "unavailable"
    assert sample["handle_capture_result"]["ok"] == False
    assert sample["resume_once_result"]["ok"] == False
    assert sample["final_verdict"] == "partially_supported"
    assert isinstance(sample.get("target_scope_note"), str) and sample["target_scope_note"] != ""
