import os

from scripts import acp_client, acp_probe


class FakeSession:
    session_id = "fake-session-1"

    def execute_turn(self, prompt):
        return {
            "ok": True,
            "status": "succeeded",
            "detail": f"fake response for {prompt}",
            "response": "pong",
            "handle": "fake-handle-1",
        }


class FakeSessionWithoutHandle:
    def execute_turn(self, _prompt):
        return {"ok": True, "status": "succeeded", "response": "pong"}


class FailingTurnSession:
    def execute_turn(self, _prompt):
        raise RuntimeError("simulated turn failure")


def test_client_connect_uses_injected_fake_transport(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    calls = []

    def fake_session_factory(**options):
        calls.append(options)
        return FakeSession()

    result = acp_client.ACPClient(session_factory=fake_session_factory).connect(mode="fake")

    assert calls == [{"mode": "fake"}]
    assert result["operation"] == "connect"
    assert result["ok"] is True
    assert result["status"] == "connected"
    assert result["metadata"]["session_id"] == "fake-session-1"
    assert result["metadata"]["sdk_package_name"] == "agent-client-protocol"


def test_sdk_import_or_initialization_failure_is_classifiable():
    def failing_session_factory(**_options):
        raise RuntimeError("simulated sdk/session setup failure")

    result = acp_client.ACPClient(session_factory=failing_session_factory).connect()

    assert result["operation"] == "connect"
    assert result["ok"] is False
    assert result["status"] == "initialization_failed"
    assert "RuntimeError" in result["error"]
    assert "Traceback" not in result["error"]

    verdict = acp_probe.emit_verdict(
        {
            "connect": result,
            "execute_turn": {"ok": False, "detail": "turn skipped after connect failure"},
            "capture_handle": {"ok": False, "detail": "handle skipped after connect failure"},
            "resume_once": {"ok": False, "detail": "resume skipped after connect failure"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )
    categories = {item["category"] for item in verdict["failure_classification"]}
    assert "Connection Failed" in categories
    assert verdict["final_verdict"] == "not_suitable_at_this_stage"


def test_client_connect_observation_can_feed_probe_verdict():
    connect_result = acp_client.connect(session_factory=lambda **_options: FakeSession())

    verdict = acp_probe.emit_verdict(
        {
            "connect": connect_result,
            "execute_turn": {"ok": False, "status": "not_implemented", "detail": "outside this slice"},
            "capture_handle": {"ok": False, "status": "not_implemented", "detail": "outside this slice"},
            "resume_once": {"ok": False, "status": "not_implemented", "detail": "outside this slice"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["connect_result"] == connect_result
    assert verdict["connect_result"]["operation"] == "connect"
    assert verdict["final_verdict"] in acp_probe.FINAL_VERDICTS


def test_execute_turn_returns_contract_observation():
    turn_result = acp_client.execute_turn("ping", session_factory=lambda **_options: FakeSession())

    assert turn_result["operation"] == "execute_turn"
    assert turn_result["ok"] is True
    assert turn_result["status"] == "succeeded"
    assert turn_result["metadata"]["response_text"] == "pong"
    assert turn_result["metadata"]["handle"] == "fake-handle-1"

    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True, "detail": "connected"},
            "execute_turn": turn_result,
            "capture_handle": {"ok": False, "status": "unavailable", "detail": "not part of this assertion"},
            "resume_once": {"ok": False, "status": "unavailable", "detail": "not part of this assertion"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["execute_turn_result"]["operation"] == "execute_turn"
    assert verdict["execute_turn_result"]["ok"] is True


def test_capture_handle_records_protocol_native_or_returned_strategy():
    handle_result = acp_client.capture_handle({"response": "pong", "handle": "fake-handle-1"})

    assert handle_result["operation"] == "capture_handle"
    assert handle_result["ok"] is True
    assert handle_result["status"] == "captured"
    assert handle_result["metadata"]["handle"] == "fake-handle-1"
    assert handle_result["metadata"]["handle_acquisition_strategy"] == "protocol_native_or_returned_handle"

    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True, "detail": "connected"},
            "execute_turn": {"ok": True, "detail": "turn completed"},
            "capture_handle": handle_result,
            "resume_once": {"ok": False, "status": "unavailable", "detail": "resume outside this slice"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    assert verdict["handle_capture_result"]["ok"] is True
    assert verdict["handle_acquisition_strategy"] in {"returned_handle", "protocol_native_or_returned_handle"}


def test_capture_handle_records_explicit_unavailable_when_no_handle():
    handle_result = acp_client.capture_handle({"response": "pong"})

    assert handle_result["operation"] == "capture_handle"
    assert handle_result["ok"] is False
    assert handle_result["status"] == "unavailable"
    assert handle_result["error"] == "Handle Unavailable"
    assert handle_result["metadata"]["handle_acquisition_strategy"] == "unavailable"


def test_turn_or_handle_failure_remains_valid_probe_verdict_input():
    turn_result = acp_client.execute_turn("ping", session_factory=lambda **_options: FailingTurnSession())
    handle_result = acp_client.capture_handle({"response": "pong"})

    verdict = acp_probe.emit_verdict(
        {
            "connect": {"ok": True, "detail": "connected"},
            "execute_turn": turn_result,
            "capture_handle": handle_result,
            "resume_once": {"ok": False, "status": "unavailable", "detail": "resume cannot run without handle"},
        },
        validation_timestamp="2026-05-25T00:00:00Z",
    )

    categories = {item["category"] for item in verdict["failure_classification"]}
    assert turn_result["ok"] is False
    assert "Turn Execution Failed" in categories
    assert "Continuation Handle Unavailable" in categories
    assert verdict["final_verdict"] in acp_probe.FINAL_VERDICTS


def test_default_turn_and_handle_tests_do_not_require_real_gemini_or_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def import_would_fail_if_real_sdk_were_used(_module_name):
        raise AssertionError("default turn and handle tests must use fake injection")

    client = acp_client.ACPClient(
        session_factory=lambda **_options: FakeSessionWithoutHandle(),
        sdk_importer=import_would_fail_if_real_sdk_were_used,
    )

    turn_result = client.execute_turn("ping")
    handle_result = client.capture_handle(turn_result)

    assert "GEMINI_API_KEY" not in os.environ
    assert turn_result["ok"] is True
    assert turn_result["operation"] == "execute_turn"
    assert handle_result["ok"] is False
    assert handle_result["status"] == "unavailable"


def test_default_client_connect_tests_do_not_require_real_gemini_or_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def import_would_fail_if_real_sdk_were_used(_module_name):
        raise AssertionError("default connect-boundary tests must use fake injection")

    result = acp_client.ACPClient(
        session_factory=lambda **_options: FakeSession(),
        sdk_importer=import_would_fail_if_real_sdk_were_used,
    ).connect()

    assert "GEMINI_API_KEY" not in os.environ
    assert result["ok"] is True
    assert result["operation"] == "connect"
