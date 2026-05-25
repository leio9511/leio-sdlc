"""Deterministic ACP probe contract mapping for Issue #50.

acp_probe.py owns minimal ACP probe logic and contract-relevant observation mapping.

This module intentionally does not launch Gemini CLI or any other process.  It
normalizes local observations into a stable verdict artifact so negative ACP
findings remain valid framework outputs instead of uncaught exceptions.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping

TARGET_CLI = "Gemini CLI"
SDK_PACKAGE_NAME = "agent-client-protocol"
SCOPE_NOTE = (
    "This PRD's ACP viability verdict applies only to the tested Gemini CLI path "
    "and must not be generalized to Codex or any other CLI."
)

FINAL_VERDICTS = {
    "supported",
    "partially_supported",
    "not_suitable_at_this_stage",
    "blocked",
}

REQUIRED_VERDICT_FIELDS = [
    "target_cli",
    "validation_timestamp",
    "connect_result",
    "execute_turn_result",
    "handle_capture_result",
    "resume_once_result",
    "failure_classification",
    "continuity_mode",
    "handle_acquisition_strategy",
    "resume_requires_same_runtime_state",
    "fallback_policy",
    "capability_surface",
    "final_verdict",
]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def operation_result(
    operation: str,
    ok: bool,
    *,
    status: str | None = None,
    detail: str = "",
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable per-operation observation shape."""

    result: dict[str, Any] = {
        "operation": operation,
        "ok": bool(ok),
        "status": status or ("succeeded" if ok else "failed"),
        "detail": detail,
    }
    if error:
        result["error"] = str(error)
    if metadata:
        result["metadata"] = dict(metadata)
    return result


def _normalize_result(operation: str, observation: Mapping[str, Any] | None, default_ok: bool) -> dict[str, Any]:
    if observation is None:
        return operation_result(operation, default_ok)

    if "ok" in observation:
        ok = bool(observation["ok"])
    elif "success" in observation:
        ok = bool(observation["success"])
    else:
        ok = default_ok

    return operation_result(
        operation,
        ok,
        status=str(observation.get("status") or ("succeeded" if ok else "failed")),
        detail=str(observation.get("detail") or observation.get("message") or ""),
        error=str(observation["error"]) if observation.get("error") else None,
        metadata=observation.get("metadata") if isinstance(observation.get("metadata"), Mapping) else None,
    )


def connect(
    observation: Mapping[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Map a connect observation, including a graceful missing API key result."""

    if observation is not None:
        return _normalize_result("connect", observation, True)

    env = os.environ if environ is None else environ
    if "GEMINI_API_KEY" not in env or not env.get("GEMINI_API_KEY"):
        return operation_result(
            "connect",
            False,
            status="blocked",
            detail="GEMINI_API_KEY is not available in the controlled environment.",
            error="Missing API Key",
        )
    return operation_result("connect", True, detail="ACP endpoint readiness prerequisite is present.")


def execute_turn(observation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Map a minimal request/response turn observation."""

    return _normalize_result("execute_turn", observation, True)


def capture_handle(
    observation: Mapping[str, Any] | None = None,
    *,
    handle: str | None = None,
) -> dict[str, Any]:
    """Map continuation/session handle acquisition."""

    if observation is not None:
        return _normalize_result("capture_handle", observation, bool(observation.get("handle") or handle))
    if handle:
        return operation_result("capture_handle", True, detail="Continuation handle captured.", metadata={"handle": handle})
    return operation_result(
        "capture_handle",
        False,
        status="unavailable",
        detail="No protocol-native or returned continuation handle was observed.",
        error="Handle Unavailable",
    )


def resume_once(
    observation: Mapping[str, Any] | None = None,
    *,
    handle: str | None = None,
) -> dict[str, Any]:
    """Map one bounded continuation/resume attempt."""

    if observation is not None:
        return _normalize_result("resume_once", observation, bool(observation.get("ok", False)))
    if handle:
        return operation_result("resume_once", True, detail="Bounded resume attempt completed.")
    return operation_result(
        "resume_once",
        False,
        status="unavailable",
        detail="Resume was not attempted because no continuation handle was available.",
        error="Resume Handle Unavailable",
    )


def classify_failure(observations: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, str]]:
    """Classify failed observations into contract-relevant categories."""

    failures: list[dict[str, str]] = []
    for name, result in (observations or {}).items():
        if result.get("ok"):
            continue
        text = " ".join(str(result.get(key, "")) for key in ("error", "detail", "status")).lower()
        if "gemini_api_key" in text or "missing api key" in text or "api key" in text:
            category = "Missing API Key"
        elif "handle" in text:
            category = "Continuation Handle Unavailable"
        elif "resume" in text:
            category = "Resume Unavailable"
        elif name == "connect_result":
            category = "Connection Failed"
        elif name == "execute_turn_result":
            category = "Turn Execution Failed"
        else:
            category = "Unclassified Failure"
        failures.append(
            {
                "operation": str(result.get("operation") or name.replace("_result", "")),
                "category": category,
                "detail": str(result.get("detail") or result.get("error") or ""),
            }
        )
    return failures


def _derive_contract_fields(results: Mapping[str, Mapping[str, Any]], failures: list[dict[str, str]]) -> dict[str, Any]:
    missing_api_key = any(item["category"] == "Missing API Key" for item in failures)
    connect_ok = bool(results["connect_result"].get("ok"))
    turn_ok = bool(results["execute_turn_result"].get("ok"))
    handle_ok = bool(results["handle_capture_result"].get("ok"))
    resume_ok = bool(results["resume_once_result"].get("ok"))

    if handle_ok and resume_ok:
        continuity_mode = "authoritative_resume"
        handle_strategy = "protocol_native"
        same_runtime_state = False
    elif handle_ok:
        continuity_mode = "unsupported"
        handle_strategy = "explicit_returned_handle"
        same_runtime_state = True
    else:
        continuity_mode = "unsupported"
        handle_strategy = "unavailable"
        same_runtime_state = True

    if missing_api_key:
        final_verdict = "blocked"
        fallback_policy = "fail_closed_until_prerequisite_ready"
    elif connect_ok and turn_ok and handle_ok and resume_ok:
        final_verdict = "supported"
        fallback_policy = "no_fallback_required"
    elif connect_ok and turn_ok and (not handle_ok or not resume_ok):
        final_verdict = "partially_supported"
        fallback_policy = "fallback_to_legacy_direct_cli_for_continuity"
    else:
        final_verdict = "not_suitable_at_this_stage"
        fallback_policy = "fallback_to_legacy_direct_cli"

    capability_surface = {
        "connect": connect_ok,
        "execute_turn": turn_ok,
        "capture_handle": handle_ok,
        "resume_once": resume_ok,
        "classify_failure": True,
        "emit_verdict": True,
        "surface_type": "mixed" if connect_ok and turn_ok and (not handle_ok or not resume_ok) else "runtime_managed",
    }

    return {
        "continuity_mode": continuity_mode,
        "handle_acquisition_strategy": handle_strategy,
        "resume_requires_same_runtime_state": same_runtime_state,
        "fallback_policy": fallback_policy,
        "capability_surface": capability_surface,
        "final_verdict": final_verdict,
    }


def emit_verdict(
    observations: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    target_cli: str = TARGET_CLI,
    validation_timestamp: str | None = None,
) -> dict[str, Any]:
    """Emit the structured ACP viability verdict artifact."""

    source = observations or {}
    results = {
        "connect_result": _normalize_result("connect", source.get("connect_result") or source.get("connect"), True),
        "execute_turn_result": _normalize_result("execute_turn", source.get("execute_turn_result") or source.get("execute_turn"), True),
        "handle_capture_result": _normalize_result(
            "capture_handle", source.get("handle_capture_result") or source.get("capture_handle"), True
        ),
        "resume_once_result": _normalize_result("resume_once", source.get("resume_once_result") or source.get("resume_once"), True),
    }
    failures = classify_failure(results)
    contract_fields = _derive_contract_fields(results, failures)
    verdict = {
        "target_cli": target_cli,
        "validation_timestamp": validation_timestamp or _utc_timestamp(),
        **results,
        "failure_classification": failures,
        **contract_fields,
        "target_scope_note": SCOPE_NOTE,
        "sdk_package_name": SDK_PACKAGE_NAME,
    }

    missing = [field for field in REQUIRED_VERDICT_FIELDS if field not in verdict]
    if missing:
        raise ValueError(f"Internal verdict contract error, missing fields: {', '.join(missing)}")
    if verdict["final_verdict"] not in FINAL_VERDICTS:
        raise ValueError(f"Internal verdict contract error, invalid final_verdict: {verdict['final_verdict']}")
    return verdict
