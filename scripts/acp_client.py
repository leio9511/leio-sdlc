"""Thin ACP SDK client boundary for connection, turn, and handle observation.

This module intentionally keeps the official ACP Python SDK import and session
initialization behind a narrow, injectable boundary.  Unit tests can provide a
fake session factory, while production callers get controlled, classifiable
observations instead of uncaught tracebacks when the SDK is missing, session
setup fails, a minimal turn fails, or no continuation handle is available.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping

SDK_PACKAGE_NAME = "agent-client-protocol"
SDK_IMPORT_MODULE = "agent_client_protocol"

ConnectObservation = dict[str, Any]
SessionFactory = Callable[..., Any]


@dataclass(frozen=True)
class ACPClient:
    """Minimal ACP client wrapper for connect/session initialization and one turn."""

    session_factory: SessionFactory | None = None
    sdk_importer: Callable[[str], Any] = importlib.import_module

    def _create_session(self, **session_options: Any) -> Any:
        factory = self.session_factory or self._load_default_session_factory()
        return factory(**session_options)

    def connect(self, **session_options: Any) -> ConnectObservation:
        """Initialize an ACP session and return a structured observation.

        No Gemini CLI process is launched here.  Callers that need real stdio
        process management should do so in the smoke/probe layer and inject an
        already suitable session factory into this boundary.
        """

        try:
            session = self._create_session(**session_options)
        except Exception as exc:  # noqa: BLE001 - controlled failure surface is intentional.
            return connect_observation(
                False,
                status="initialization_failed",
                detail="ACP SDK import or session initialization failed.",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME},
            )

        metadata: dict[str, Any] = {"sdk_package_name": SDK_PACKAGE_NAME}
        handle = _extract_handle(session)
        if handle is not None:
            metadata["session_id"] = str(handle)

        return connect_observation(
            True,
            status="connected",
            detail="ACP session initialized through the configured session factory.",
            metadata=metadata,
        )

    def execute_turn(self, prompt: str, **session_options: Any) -> ConnectObservation:
        """Execute one minimal request/response loop and normalize the result.

        The concrete SDK method name is intentionally treated as an injectable
        boundary: fake sessions and SDK sessions may expose one of a small set of
        likely single-turn methods.  Failures are returned as observations rather
        than uncaught exceptions so probe verdict generation remains stable.
        """

        try:
            session = self._create_session(**session_options)
            method = _find_callable(session, ("execute_turn", "send", "request", "prompt", "run"))
            if method is None:
                raise RuntimeError("No supported single-turn method found on ACP session.")
            response = method(prompt)
        except Exception as exc:  # noqa: BLE001 - controlled failure surface is intentional.
            return turn_observation(
                False,
                status="failed",
                detail="ACP minimal request/response turn failed.",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME},
            )

        return turn_observation_from_response(response)

    def capture_handle(self, response: Any | None = None, **session_options: Any) -> ConnectObservation:
        """Capture a continuation/session handle or return explicit unavailable.

        Missing continuation is valid framework evidence.  It is represented as
        a structured unavailable observation rather than an exception.
        """

        try:
            if response is None:
                response = self._create_session(**session_options)
        except Exception as exc:  # noqa: BLE001 - controlled failure surface is intentional.
            return handle_observation(
                False,
                status="failed",
                detail="ACP session initialization failed before handle capture.",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME},
            )

        handle = _extract_handle(response)
        if handle is None:
            return handle_observation(
                False,
                status="unavailable",
                detail="No protocol-native or returned continuation handle was observed.",
                error="Handle Unavailable",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME, "handle_acquisition_strategy": "unavailable"},
            )

        return handle_observation(
            True,
            status="captured",
            detail="Continuation handle captured from protocol-native or returned response data.",
            metadata={
                "sdk_package_name": SDK_PACKAGE_NAME,
                "handle": str(handle),
                "handle_acquisition_strategy": "protocol_native_or_returned_handle",
            },
        )

    def resume_once(self, handle: Any | None = None, prompt: str | None = None, **session_options: Any) -> ConnectObservation:
        """Attempt exactly one bounded continuation/resume operation.

        Missing handles and SDK/session resume failures are returned as structured
        observations.  This method intentionally performs one direct call only;
        it does not start retry loops, continuation loops, or orchestration.
        """

        if handle is None:
            return resume_observation(
                False,
                status="unavailable",
                detail="Resume was not attempted because no continuation handle was available.",
                error="Resume Handle Unavailable",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME, "attempt_count": 0},
            )

        try:
            session = self._create_session(**session_options)
            method = _find_callable(session, ("resume_once", "resume", "continue_session", "continue_turn"))
            if method is None:
                raise RuntimeError("No supported bounded resume method found on ACP session.")
            if prompt is None:
                response = method(handle)
            else:
                response = method(handle, prompt)
        except Exception as exc:  # noqa: BLE001 - controlled failure surface is intentional.
            return resume_observation(
                False,
                status="failed",
                detail="ACP bounded resume attempt failed.",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME, "handle": str(handle), "attempt_count": 1},
            )

        return resume_observation_from_response(response, handle=handle)

    def _load_default_session_factory(self) -> SessionFactory:
        """Load a likely session constructor from the official SDK module."""

        sdk = self.sdk_importer(SDK_IMPORT_MODULE)
        for attribute in ("ClientSession", "Session", "ACPClientSession"):
            factory = getattr(sdk, attribute, None)
            if callable(factory):
                return factory
        raise RuntimeError(
            "No supported ACP session factory found in agent_client_protocol; "
            "inject session_factory for this environment."
        )


def _mapping_value(source: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = source.get(key)
        if value is not None:
            return value
    return None


def _attribute_value(source: Any, keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = getattr(source, key, None)
        if value is not None:
            return value
    return None


def _extract_handle(source: Any) -> Any | None:
    keys = ("continuation_handle", "session_handle", "handle", "session_id", "id")
    if isinstance(source, Mapping):
        direct = _mapping_value(source, keys)
        if direct is not None:
            return direct
        metadata = source.get("metadata")
        if isinstance(metadata, Mapping):
            return _mapping_value(metadata, keys)
        return None
    return _attribute_value(source, keys)


def _extract_response_text(response: Any) -> str:
    if isinstance(response, Mapping):
        value = _mapping_value(response, ("response", "content", "text", "message", "output", "detail"))
        return str(value) if value is not None else ""
    value = _attribute_value(response, ("response", "content", "text", "message", "output", "detail"))
    return str(value) if value is not None else str(response)


def _find_callable(source: Any, names: tuple[str, ...]) -> Callable[..., Any] | None:
    for name in names:
        candidate = getattr(source, name, None)
        if callable(candidate):
            return candidate
    return None


def _response_metadata(response: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"sdk_package_name": SDK_PACKAGE_NAME}
    text = _extract_response_text(response)
    if text:
        metadata["response_text"] = text
    handle = _extract_handle(response)
    if handle is not None:
        metadata["handle"] = str(handle)
    if isinstance(response, Mapping):
        existing = response.get("metadata")
        if isinstance(existing, Mapping):
            metadata.update(dict(existing))
    return metadata


def connect_observation(
    ok: bool,
    *,
    status: str | None = None,
    detail: str = "",
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ConnectObservation:
    """Return the stable connect observation shape consumed by acp_probe."""

    observation: ConnectObservation = {
        "operation": "connect",
        "ok": bool(ok),
        "status": status or ("connected" if ok else "failed"),
        "detail": detail,
    }
    if error:
        observation["error"] = error
    if metadata:
        observation["metadata"] = dict(metadata)
    return observation


def turn_observation(
    ok: bool,
    *,
    status: str | None = None,
    detail: str = "",
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ConnectObservation:
    """Return the stable execute_turn observation shape consumed by acp_probe."""

    observation = connect_observation(
        ok,
        status=status or ("succeeded" if ok else "failed"),
        detail=detail,
        error=error,
        metadata=metadata,
    )
    observation["operation"] = "execute_turn"
    return observation


def turn_observation_from_response(response: Any) -> ConnectObservation:
    """Normalize fake/SDK turn response data into an execute_turn observation."""

    if isinstance(response, Mapping) and "ok" in response:
        ok = bool(response["ok"])
        status = str(response.get("status") or ("succeeded" if ok else "failed"))
        detail = str(response.get("detail") or response.get("message") or "ACP minimal request/response turn completed.")
        error = str(response["error"]) if response.get("error") else None
    else:
        ok = True
        status = "succeeded"
        detail = "ACP minimal request/response turn completed."
        error = None
    return turn_observation(ok, status=status, detail=detail, error=error, metadata=_response_metadata(response))


def handle_observation(
    ok: bool,
    *,
    status: str | None = None,
    detail: str = "",
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ConnectObservation:
    """Return the stable capture_handle observation shape consumed by acp_probe."""

    observation = connect_observation(
        ok,
        status=status or ("captured" if ok else "unavailable"),
        detail=detail,
        error=error,
        metadata=metadata,
    )
    observation["operation"] = "capture_handle"
    return observation


def resume_observation(
    ok: bool,
    *,
    status: str | None = None,
    detail: str = "",
    error: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ConnectObservation:
    """Return the stable resume_once observation shape consumed by acp_probe."""

    observation = connect_observation(
        ok,
        status=status or ("succeeded" if ok else "failed"),
        detail=detail,
        error=error,
        metadata=metadata,
    )
    observation["operation"] = "resume_once"
    return observation


def resume_observation_from_response(response: Any, *, handle: Any) -> ConnectObservation:
    """Normalize fake/SDK resume response data into a resume_once observation."""

    if isinstance(response, Mapping) and "ok" in response:
        ok = bool(response["ok"])
        status = str(response.get("status") or ("succeeded" if ok else "failed"))
        detail = str(response.get("detail") or response.get("message") or "ACP bounded resume attempt completed.")
        error = str(response["error"]) if response.get("error") else None
    else:
        ok = True
        status = "succeeded"
        detail = "ACP bounded resume attempt completed."
        error = None
    metadata = _response_metadata(response)
    metadata["handle"] = str(handle)
    metadata["attempt_count"] = 1
    return resume_observation(ok, status=status, detail=detail, error=error, metadata=metadata)


def connect(
    *,
    session_factory: SessionFactory | None = None,
    sdk_importer: Callable[[str], Any] = importlib.import_module,
    **session_options: Any,
) -> ConnectObservation:
    """Convenience function for one-shot connect-boundary callers."""

    return ACPClient(session_factory=session_factory, sdk_importer=sdk_importer).connect(**session_options)


def execute_turn(
    prompt: str,
    *,
    session_factory: SessionFactory | None = None,
    sdk_importer: Callable[[str], Any] = importlib.import_module,
    **session_options: Any,
) -> ConnectObservation:
    """Convenience function for one-shot minimal turn callers."""

    return ACPClient(session_factory=session_factory, sdk_importer=sdk_importer).execute_turn(prompt, **session_options)


def capture_handle(
    response: Any | None = None,
    *,
    session_factory: SessionFactory | None = None,
    sdk_importer: Callable[[str], Any] = importlib.import_module,
    **session_options: Any,
) -> ConnectObservation:
    """Convenience function for one-shot handle capture callers."""

    return ACPClient(session_factory=session_factory, sdk_importer=sdk_importer).capture_handle(response, **session_options)


def resume_once(
    handle: Any | None = None,
    prompt: str | None = None,
    *,
    session_factory: SessionFactory | None = None,
    sdk_importer: Callable[[str], Any] = importlib.import_module,
    **session_options: Any,
) -> ConnectObservation:
    """Convenience function for one-shot bounded resume callers."""

    return ACPClient(session_factory=session_factory, sdk_importer=sdk_importer).resume_once(
        handle, prompt, **session_options
    )
