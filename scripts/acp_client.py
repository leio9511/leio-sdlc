"""Thin ACP SDK client boundary for connection initialization only.

This module intentionally keeps the official ACP Python SDK import and session
initialization behind a narrow, injectable boundary.  Unit tests can provide a
fake session factory, while production callers get a controlled, classifiable
connect observation instead of an uncaught traceback when the SDK is missing or
session setup fails.
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
    """Minimal ACP client wrapper for connect/session initialization only."""

    session_factory: SessionFactory | None = None
    sdk_importer: Callable[[str], Any] = importlib.import_module

    def connect(self, **session_options: Any) -> ConnectObservation:
        """Initialize an ACP session and return a structured observation.

        No Gemini CLI process is launched here.  Callers that need real stdio
        process management should do so in the smoke/probe layer and inject an
        already suitable session factory into this boundary.
        """

        try:
            factory = self.session_factory or self._load_default_session_factory()
            session = factory(**session_options)
        except Exception as exc:  # noqa: BLE001 - controlled failure surface is intentional.
            return connect_observation(
                False,
                status="initialization_failed",
                detail="ACP SDK import or session initialization failed.",
                error=f"{exc.__class__.__name__}: {exc}",
                metadata={"sdk_package_name": SDK_PACKAGE_NAME},
            )

        metadata: dict[str, Any] = {"sdk_package_name": SDK_PACKAGE_NAME}
        handle = getattr(session, "session_id", None) or getattr(session, "id", None)
        if handle is not None:
            metadata["session_id"] = str(handle)

        return connect_observation(
            True,
            status="connected",
            detail="ACP session initialized through the configured session factory.",
            metadata=metadata,
        )

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


def connect(
    *,
    session_factory: SessionFactory | None = None,
    sdk_importer: Callable[[str], Any] = importlib.import_module,
    **session_options: Any,
) -> ConnectObservation:
    """Convenience function for one-shot connect-boundary callers."""

    return ACPClient(session_factory=session_factory, sdk_importer=sdk_importer).connect(**session_options)
