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


def test_requirements_declares_agent_client_protocol():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "agent-client-protocol" in {line.strip() for line in requirements}
