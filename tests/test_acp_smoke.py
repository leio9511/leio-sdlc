import json
import subprocess
from pathlib import Path

from scripts import acp_probe, acp_smoke


class FakeProcess:
    stdin = object()
    stdout = object()
    stderr = object()

    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


class FakeClient:
    def __init__(self, *, handle="fake-handle-1", resume_ok=True):
        self.handle = handle
        self.resume_ok = resume_ok
        self.session_options = []

    def connect(self, **session_options):
        self.session_options.append(session_options)
        return {
            "operation": "connect",
            "ok": True,
            "status": "connected",
            "detail": "fake Gemini ACP stdio connected",
            "metadata": {"launch_command": session_options["launch_command"], "transport": "stdio"},
        }

    def execute_turn(self, prompt, **_session_options):
        metadata = {"response_text": f"pong for {prompt}"}
        if self.handle:
            metadata["handle"] = self.handle
        return {
            "operation": "execute_turn",
            "ok": True,
            "status": "succeeded",
            "detail": "fake Gemini ACP turn completed",
            "metadata": metadata,
        }

    def capture_handle(self, response, **_session_options):
        if not self.handle:
            return {
                "operation": "capture_handle",
                "ok": False,
                "status": "unavailable",
                "detail": "fake response did not include a continuation handle",
                "error": "Handle Unavailable",
            }
        return {
            "operation": "capture_handle",
            "ok": True,
            "status": "captured",
            "detail": "fake handle captured",
            "metadata": {"handle": self.handle},
        }

    def resume_once(self, handle, prompt, **_session_options):
        if not self.resume_ok:
            return {
                "operation": "resume_once",
                "ok": False,
                "status": "failed",
                "detail": f"fake continuation failure for {prompt}",
                "error": "Resume Unavailable",
                "metadata": {"handle": handle, "attempt_count": 1},
            }
        return {
            "operation": "resume_once",
            "ok": True,
            "status": "succeeded",
            "detail": "fake resume completed",
            "metadata": {"handle": handle, "attempt_count": 1},
        }


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_smoke_builds_gemini_acp_stdio_launch_command():
    command = acp_smoke.build_gemini_acp_stdio_launch_command(extra_args=["--profile", "sdlc-smoke"])

    assert command[0] == "gemini"
    assert "--acp" in command
    assert "codex" not in command
    assert "claude" not in command


def test_smoke_writes_timestamped_and_latest_artifacts(tmp_path):
    launched = []
    fake_process = FakeProcess()

    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))
        return fake_process

    result = acp_smoke.run_smoke(
        repo_root=tmp_path,
        environ={"GEMINI_API_KEY": "test-key"},
        timestamp="2026-05-25T00:00:00Z",
        popen_factory=fake_popen,
        client_factory=lambda: FakeClient(),
    )

    assert launched[0][0] == ["gemini", "--acp"]
    assert launched[0][1]["stdin"] == subprocess.PIPE
    assert launched[0][1]["stdout"] == subprocess.PIPE
    assert launched[0][1]["stderr"] == subprocess.PIPE
    assert result.timestamped_path == tmp_path / ".sdlc_runs" / "acp" / "gemini" / "20260525T000000Z.json"
    assert result.latest_path == tmp_path / ".sdlc_runs" / "acp" / "gemini" / "latest.json"
    assert result.timestamped_path.exists()
    assert result.latest_path.exists()
    assert _read_json(result.timestamped_path) == _read_json(result.latest_path)
    assert set(acp_probe.REQUIRED_VERDICT_FIELDS).issubset(_read_json(result.latest_path))
    assert fake_process.terminated is True


def test_missing_gemini_api_key_emits_blocked_artifact_without_traceback(tmp_path):
    def popen_should_not_run(*_args, **_kwargs):
        raise AssertionError("missing GEMINI_API_KEY must not launch Gemini CLI")

    result = acp_smoke.run_smoke(
        repo_root=tmp_path,
        environ={},
        timestamp="2026-05-25T00:00:00Z",
        popen_factory=popen_should_not_run,
    )

    artifact = _read_json(result.latest_path)
    categories = {item["category"] for item in artifact["failure_classification"]}
    assert "Missing API Key" in categories
    assert artifact["final_verdict"] in {"blocked", "partially_supported"}
    assert "Traceback" not in json.dumps(artifact)


def test_unavailable_gemini_cli_is_non_blocking_structured_verdict(tmp_path):
    def fake_popen(_command, **_kwargs):
        raise FileNotFoundError("gemini not found")

    result = acp_smoke.run_smoke(
        repo_root=tmp_path,
        environ={"GEMINI_API_KEY": "test-key"},
        timestamp="2026-05-25T00:00:00Z",
        popen_factory=fake_popen,
    )

    artifact = _read_json(result.latest_path)
    assert artifact["connect_result"]["ok"] is False
    assert artifact["final_verdict"] == "not_suitable_at_this_stage"
    assert set(acp_probe.REQUIRED_VERDICT_FIELDS).issubset(artifact)
    assert "Traceback" not in json.dumps(artifact)


def test_negative_resume_verdict_does_not_fail_default_smoke_tests(tmp_path):
    result = acp_smoke.run_smoke(
        repo_root=tmp_path,
        environ={"GEMINI_API_KEY": "test-key"},
        timestamp="2026-05-25T00:00:00Z",
        popen_factory=lambda _command, **_kwargs: FakeProcess(),
        client_factory=lambda: FakeClient(resume_ok=False),
    )

    artifact = _read_json(result.latest_path)
    assert artifact["resume_once_result"]["ok"] is False
    assert artifact["final_verdict"] == "partially_supported"
    assert {item["category"] for item in artifact["failure_classification"]} >= {"Resume Unavailable"}


def test_runtime_artifacts_are_not_written_to_tests_fixtures(tmp_path):
    result = acp_smoke.run_smoke(
        repo_root=tmp_path,
        environ={"GEMINI_API_KEY": "test-key"},
        timestamp="2026-05-25T00:00:00Z",
        popen_factory=lambda _command, **_kwargs: FakeProcess(),
        client_factory=lambda: FakeClient(),
    )

    assert result.latest_path.parent == tmp_path / ".sdlc_runs" / "acp" / "gemini"
    assert "tests/fixtures" not in result.latest_path.as_posix()
    assert not (tmp_path / "tests" / "fixtures" / "latest.json").exists()
