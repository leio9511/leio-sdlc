"""Controlled Gemini CLI ACP smoke runner and runtime artifact writer.

acp_smoke.py owns the controlled smoke/exploratory runner for Gemini CLI and
writes structured verdict artifacts.

The default runner keeps real Gemini probing outside default automated tests: it
uses explicit subprocess stdio launch construction, injectable process/client
boundaries, and always emits a structured verdict artifact for missing
prerequisites or negative ACP observations.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from scripts import acp_client, acp_probe

TARGET_CLI = "Gemini CLI"
TARGET_SLUG = "gemini"
DEFAULT_GEMINI_EXECUTABLE = "gemini"
DEFAULT_PROMPT = "Reply with pong for an ACP smoke validation."
DEFAULT_RESUME_PROMPT = "Continue the ACP smoke validation once."
RUNTIME_ARTIFACT_DIR = Path(".sdlc_runs") / "acp" / TARGET_SLUG
LATEST_ARTIFACT_NAME = "latest.json"

ProcessFactory = Callable[..., Any]
ClientFactory = Callable[..., acp_client.ACPClient]


@dataclass(frozen=True)
class SmokeResult:
    """Structured smoke-run return value."""

    verdict: dict[str, Any]
    timestamped_path: Path
    latest_path: Path


def utc_timestamp() -> str:
    """Return a stable UTC timestamp for verdict content."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_to_filename(timestamp: str) -> str:
    """Convert an ISO timestamp to a filesystem-safe JSON artifact name."""

    safe = timestamp.replace(":", "").replace("-", "").replace("Z", "Z")
    safe = safe.replace(".", "")
    return f"{safe}.json"


def build_gemini_acp_stdio_launch_command(
    *,
    executable: str = DEFAULT_GEMINI_EXECUTABLE,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    """Build the explicit Gemini CLI ACP stdio launch command."""

    command = [executable, "--acp"]
    if extra_args:
        command.extend(str(arg) for arg in extra_args)
    return command


def runtime_artifact_dir(repo_root: Path | str = Path.cwd()) -> Path:
    """Return the mandated runtime artifact directory for real Gemini verdicts."""

    return Path(repo_root) / RUNTIME_ARTIFACT_DIR


def write_verdict_artifacts(
    verdict: Mapping[str, Any],
    *,
    repo_root: Path | str = Path.cwd(),
) -> tuple[Path, Path]:
    """Write timestamped and latest verdict artifacts with identical JSON content."""

    artifact_dir = runtime_artifact_dir(repo_root)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    timestamp = str(verdict["validation_timestamp"])
    timestamped_path = artifact_dir / timestamp_to_filename(timestamp)
    latest_path = artifact_dir / LATEST_ARTIFACT_NAME
    payload = json.dumps(dict(verdict), indent=2, sort_keys=True) + "\n"

    timestamped_tmp = timestamped_path.with_suffix(timestamped_path.suffix + ".tmp")
    latest_tmp = latest_path.with_suffix(latest_path.suffix + ".tmp")
    timestamped_tmp.write_text(payload, encoding="utf-8")
    timestamped_tmp.replace(timestamped_path)
    latest_tmp.write_text(payload, encoding="utf-8")
    latest_tmp.replace(latest_path)
    return timestamped_path, latest_path


def _skipped_result(operation: str, detail: str, *, error: str | None = None) -> dict[str, Any]:
    return acp_probe.operation_result(operation, False, status="skipped", detail=detail, error=error)


def _missing_api_key_verdict(timestamp: str) -> dict[str, Any]:
    connect_result = acp_probe.connect(environ={})
    return acp_probe.emit_verdict(
        {
            "connect": connect_result,
            "execute_turn": _skipped_result("execute_turn", "turn skipped because GEMINI_API_KEY is missing"),
            "capture_handle": _skipped_result("capture_handle", "handle capture skipped because GEMINI_API_KEY is missing"),
            "resume_once": _skipped_result("resume_once", "resume skipped because GEMINI_API_KEY is missing"),
        },
        target_cli=TARGET_CLI,
        validation_timestamp=timestamp,
    )


def _cli_unavailable_verdict(timestamp: str, error: BaseException) -> dict[str, Any]:
    connect_result = acp_probe.operation_result(
        "connect",
        False,
        status="unavailable",
        detail="Gemini CLI ACP subprocess could not be launched.",
        error=f"{error.__class__.__name__}: {error}",
    )
    return acp_probe.emit_verdict(
        {
            "connect": connect_result,
            "execute_turn": _skipped_result("execute_turn", "turn skipped because Gemini CLI launch failed"),
            "capture_handle": _skipped_result("capture_handle", "handle capture skipped because Gemini CLI launch failed"),
            "resume_once": _skipped_result("resume_once", "resume skipped because Gemini CLI launch failed"),
        },
        target_cli=TARGET_CLI,
        validation_timestamp=timestamp,
    )


def _extract_handle(handle_result: Mapping[str, Any], turn_result: Mapping[str, Any]) -> str | None:
    for result in (handle_result, turn_result):
        metadata = result.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("handle"):
            return str(metadata["handle"])
        if result.get("handle"):
            return str(result["handle"])
    return None


def run_smoke(
    *,
    repo_root: Path | str = Path.cwd(),
    environ: Mapping[str, str] | None = None,
    executable: str = DEFAULT_GEMINI_EXECUTABLE,
    extra_args: Sequence[str] | None = None,
    prompt: str = DEFAULT_PROMPT,
    resume_prompt: str = DEFAULT_RESUME_PROMPT,
    timestamp: str | None = None,
    popen_factory: ProcessFactory = subprocess.Popen,
    client_factory: ClientFactory | None = None,
) -> SmokeResult:
    """Run the controlled Gemini ACP smoke and always write verdict artifacts.

    A negative or blocked target verdict is a successful framework outcome.  The
    caller can inspect ``result.verdict["final_verdict"]`` without treating
    target-side ACP limitations as uncaught process failures.
    """

    env = os.environ if environ is None else environ
    validation_timestamp = timestamp or utc_timestamp()

    if not env.get("GEMINI_API_KEY"):
        verdict = _missing_api_key_verdict(validation_timestamp)
        timestamped_path, latest_path = write_verdict_artifacts(verdict, repo_root=repo_root)
        return SmokeResult(verdict=verdict, timestamped_path=timestamped_path, latest_path=latest_path)

    command = build_gemini_acp_stdio_launch_command(executable=executable, extra_args=extra_args)
    process = None
    try:
        process = popen_factory(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(env),
        )
    except (FileNotFoundError, OSError) as exc:
        verdict = _cli_unavailable_verdict(validation_timestamp, exc)
        timestamped_path, latest_path = write_verdict_artifacts(verdict, repo_root=repo_root)
        return SmokeResult(verdict=verdict, timestamped_path=timestamped_path, latest_path=latest_path)

    try:
        client = client_factory() if client_factory is not None else acp_client.ACPClient(
            session_factory=acp_client.stdio_session_factory(
                process=process,
                stdin=getattr(process, "stdin", None),
                stdout=getattr(process, "stdout", None),
                stderr=getattr(process, "stderr", None),
                launch_command=command,
                target_cli=TARGET_CLI,
            )
        )
        session_options = {
            "process": process,
            "stdin": getattr(process, "stdin", None),
            "stdout": getattr(process, "stdout", None),
            "stderr": getattr(process, "stderr", None),
            "launch_command": command,
            "target_cli": TARGET_CLI,
            "transport": "stdio",
        }
        connect_result = client.connect(**session_options)
        if connect_result.get("ok"):
            turn_result = client.execute_turn(prompt, **session_options)
        else:
            turn_result = _skipped_result("execute_turn", "turn skipped because ACP connect failed")

        if turn_result.get("ok"):
            handle_result = client.capture_handle(turn_result, **session_options)
        else:
            handle_result = _skipped_result("capture_handle", "handle capture skipped because execute_turn failed")

        handle = _extract_handle(handle_result, turn_result)
        if handle:
            resume_result = client.resume_once(handle, resume_prompt, **session_options)
        else:
            resume_result = acp_client.resume_observation(
                False,
                status="unavailable",
                detail="Resume was not attempted because no continuation handle was available.",
                error="Resume Handle Unavailable",
                metadata={"attempt_count": 0},
            )

        verdict = acp_probe.emit_verdict(
            {
                "connect": connect_result,
                "execute_turn": turn_result,
                "capture_handle": handle_result,
                "resume_once": resume_result,
            },
            target_cli=TARGET_CLI,
            validation_timestamp=validation_timestamp,
        )
    except Exception as exc:  # noqa: BLE001 - smoke must emit structured artifact, not traceback-only output.
        verdict = _cli_unavailable_verdict(validation_timestamp, exc)
    finally:
        if process is not None:
            terminate = getattr(process, "terminate", None)
            if callable(terminate):
                terminate()

    timestamped_path, latest_path = write_verdict_artifacts(verdict, repo_root=repo_root)
    return SmokeResult(verdict=verdict, timestamped_path=timestamped_path, latest_path=latest_path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the controlled Gemini CLI ACP smoke validation.")
    parser.add_argument("--repo-root", default=Path.cwd(), type=Path)
    parser.add_argument("--gemini-executable", default=DEFAULT_GEMINI_EXECUTABLE)
    parser.add_argument("--extra-arg", action="append", default=[])
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--resume-prompt", default=DEFAULT_RESUME_PROMPT)
    args = parser.parse_args(argv)

    result = run_smoke(
        repo_root=args.repo_root,
        executable=args.gemini_executable,
        extra_args=args.extra_arg,
        prompt=args.prompt,
        resume_prompt=args.resume_prompt,
    )
    print(json.dumps(result.verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    raise SystemExit(main())
