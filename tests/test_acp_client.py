import os

from scripts import acp_client, acp_probe


class FakeSession:
    session_id = "fake-session-1"


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
