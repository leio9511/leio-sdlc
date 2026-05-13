"""Unit tests for bootstrap artifact lifecycle and authoritative classification — PR-002."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

import bootstrap_artifact as ba


# ── Helpers ─────────────────────────────────────────────────────────────

@pytest.fixture
def run_dir():
    """Create a temporary run directory for isolated artifact I/O."""
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def invocation_id():
    return "abc123"


# ══════════════════════════════════════════════════════════════════════════
# Authoritative vs. heuristic classification
# ══════════════════════════════════════════════════════════════════════════

class TestClassifyResumeSource:
    """TC 1-4: classify_resume_source returns correct classification."""

    def test_authoritative_cli_runtime(self):
        """TC-1: 'cli_runtime' is classified as authoritative."""
        assert ba.classify_resume_source("cli_runtime") == "authoritative"

    def test_authoritative_provider_handle(self):
        """TC-2: 'provider_handle' is classified as authoritative."""
        assert ba.classify_resume_source("provider_handle") == "authoritative"

    def test_heuristic_text_parsed(self):
        """TC-3: 'text_parsed' is classified as heuristic."""
        assert ba.classify_resume_source("text_parsed") == "heuristic"

    def test_heuristic_unknown(self):
        """TC-4: unknown source label is classified as heuristic."""
        assert ba.classify_resume_source("latest_index_guess") == "heuristic"


# ══════════════════════════════════════════════════════════════════════════
# Artifact write + read (success / failure)
# ══════════════════════════════════════════════════════════════════════════

class TestWriteAndReadBootstrapArtifact:
    """TC 5-6: write and read bootstrap artifacts round-trip correctly."""

    def test_write_and_read_success(self, run_dir, invocation_id):
        """TC-5: write success artifact → read back → verify all fields."""
        result_path = ba.write_bootstrap_success(
            run_dir=run_dir,
            invocation_id=invocation_id,
            engine="gemini",
            resume_handle="sess_001",
            resume_kind="session_id",
            source="cli_runtime",
            captured_at="2026-05-13T10:00:00+00:00",
        )
        assert result_path == ba.get_bootstrap_artifact_path(run_dir, invocation_id)
        assert os.path.exists(result_path)

        artifact = ba.read_bootstrap_artifact(run_dir, invocation_id)
        assert artifact["ok"] is True
        assert artifact["authoritative"] is True
        assert artifact["engine"] == "gemini"
        assert artifact["resume_handle"] == "sess_001"
        assert artifact["resume_kind"] == "session_id"
        assert artifact["source"] == "cli_runtime"
        assert artifact["captured_at"] == "2026-05-13T10:00:00+00:00"
        assert artifact["phase"] == "bootstrap"

    def test_write_and_read_failure(self, run_dir, invocation_id):
        """TC-6: write failure artifact → read back → verify failure shape."""
        result_path = ba.write_bootstrap_failure(
            run_dir=run_dir,
            invocation_id=invocation_id,
            engine="gemini",
            failure_reason="missing_authoritative_resume_handle",
        )
        assert result_path == ba.get_bootstrap_artifact_path(run_dir, invocation_id)
        assert os.path.exists(result_path)

        artifact = ba.read_bootstrap_artifact(run_dir, invocation_id)
        assert artifact["ok"] is False
        assert artifact["authoritative"] is False
        assert artifact["resume_handle"] is None
        assert artifact["resume_kind"] is None
        assert artifact["source"] is None
        assert artifact["captured_at"] is None
        assert artifact["failure_reason"] == "missing_authoritative_resume_handle"
        assert artifact["phase"] == "bootstrap"

    def test_read_nonexistent_artifact_raises(self, run_dir):
        """TC-a: reading a non-existent artefact raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ba.read_bootstrap_artifact(run_dir, "no_such_id")


# ══════════════════════════════════════════════════════════════════════════
# is_bootstrap_successful / is_bootstrap_failed
# ══════════════════════════════════════════════════════════════════════════

class TestBootstrapStatusPredicates:
    """TC 7-9: status predicates on artefact dicts."""

    def test_is_successful_true(self):
        """TC-7: ok=True + authoritative=True → successful."""
        assert ba.is_bootstrap_successful({"ok": True, "authoritative": True}) is True

    def test_is_successful_false_when_not_authoritative(self):
        """TC-8: ok=True + authoritative=False → not successful."""
        assert ba.is_bootstrap_successful({"ok": True, "authoritative": False}) is False

    def test_is_successful_false_when_not_ok(self):
        """TC-9: ok=False → not successful."""
        assert ba.is_bootstrap_successful({"ok": False}) is False

    def test_is_successful_false_when_ok_missing(self):
        """Edge: ok key missing → not successful."""
        assert ba.is_bootstrap_successful({"authoritative": True}) is False

    def test_is_failed_true(self):
        """TC-b: ok=False → failed."""
        assert ba.is_bootstrap_failed({"ok": False}) is True

    def test_is_failed_false_for_success(self):
        """TC-c: ok=True → not failed."""
        assert ba.is_bootstrap_failed({"ok": True}) is False


# ══════════════════════════════════════════════════════════════════════════
# Directory & path construction
# ══════════════════════════════════════════════════════════════════════════

class TestPathConstruction:
    """TC 10-11: path builders produce exact expected paths."""

    def test_bootstrap_dir_path(self):
        """TC-10: get_bootstrap_dir → <run_dir>/bootstrap/"""
        assert ba.get_bootstrap_dir("/path/to/run") == "/path/to/run/bootstrap/"

    def test_bootstrap_artifact_path(self):
        """TC-11: get_bootstrap_artifact_path → <run_dir>/bootstrap/<id>.json"""
        assert (
            ba.get_bootstrap_artifact_path("/path/to/run", "abc123")
            == "/path/to/run/bootstrap/abc123.json"
        )

    def test_bootstrap_index_path(self):
        """TC-d: get_bootstrap_index_path → <run_dir>/bootstrap_index.json"""
        assert (
            ba.get_bootstrap_index_path("/path/to/run")
            == "/path/to/run/bootstrap_index.json"
        )


# ══════════════════════════════════════════════════════════════════════════
# Index artefact write + read + resolve
# ══════════════════════════════════════════════════════════════════════════

class TestBootstrapIndex:
    """TC 12-13: index artefact lifecycle."""

    def test_write_and_read_index(self, run_dir, invocation_id):
        """TC-12: write index → read back → targets match."""
        targets = {"coder": f"bootstrap/{invocation_id}.json"}
        path = ba.write_bootstrap_index(run_dir, targets)
        assert path == ba.get_bootstrap_index_path(run_dir)
        assert os.path.exists(path)

        index = ba.read_bootstrap_index(run_dir)
        assert index["active_targets"] == targets

    def test_resolve_active_bootstrap_artifact(self, run_dir, invocation_id):
        """TC-13: write index + artifact → resolve → read artefact."""
        ba.write_bootstrap_success(
            run_dir=run_dir,
            invocation_id=invocation_id,
            engine="openclaw",
            resume_handle="session_key_42",
            resume_kind="session_id",
            source="cli_runtime",
            captured_at="2026-05-13T10:05:00+00:00",
        )
        ba.write_bootstrap_index(
            run_dir,
            {"coder": f"bootstrap/{invocation_id}.json"},
        )

        artifact = ba.resolve_active_bootstrap_artifact(run_dir, "coder")
        assert artifact["ok"] is True
        assert artifact["resume_handle"] == "session_key_42"


# ══════════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════════

class TestValidateBootstrapArtifact:
    """TC 14-16: schema validation."""

    def test_validate_empty_dict(self):
        """TC-14: empty dict returns non-empty error list."""
        errors = ba.validate_bootstrap_artifact({})
        assert len(errors) > 0

    def test_validate_valid_success(self):
        """TC-15: valid success artefact → empty error list."""
        artifact = {
            "engine": "gemini",
            "ok": True,
            "phase": "bootstrap",
            "authoritative": True,
            "resume_handle": "sess_001",
            "resume_kind": "session_id",
            "source": "cli_runtime",
            "captured_at": "2026-05-13T10:00:00+00:00",
            "failure_reason": None,
        }
        assert ba.validate_bootstrap_artifact(artifact) == []

    def test_validate_valid_failure(self):
        """TC-16: valid failure artefact → empty error list."""
        artifact = {
            "engine": "gemini",
            "ok": False,
            "phase": "bootstrap",
            "authoritative": False,
            "resume_handle": None,
            "resume_kind": None,
            "source": None,
            "captured_at": None,
            "failure_reason": "missing_authoritative_resume_handle",
        }
        assert ba.validate_bootstrap_artifact(artifact) == []

    def test_write_success_validates(self, run_dir, invocation_id):
        """Integration: write_bootstrap_success → validate passes (reviewer finding #1)."""
        ba.write_bootstrap_success(
            run_dir=run_dir,
            invocation_id=invocation_id,
            engine="gemini",
            resume_handle="sess_002",
            resume_kind="session_id",
            source="cli_runtime",
            captured_at="2026-05-13T10:00:00+00:00",
        )
        artifact = ba.read_bootstrap_artifact(run_dir, invocation_id)
        errors = ba.validate_bootstrap_artifact(artifact)
        assert errors == [], f"validation errors on real success artifact: {errors}"

    def test_write_failure_validates(self, run_dir, invocation_id):
        """Integration: write_bootstrap_failure → validate passes (reviewer finding #1)."""
        ba.write_bootstrap_failure(
            run_dir=run_dir,
            invocation_id=invocation_id,
            engine="gemini",
            failure_reason="timeout",
        )
        artifact = ba.read_bootstrap_artifact(run_dir, invocation_id)
        errors = ba.validate_bootstrap_artifact(artifact)
        assert errors == [], f"validation errors on real failure artifact: {errors}"

    def test_write_index_validates_run_dir_must_exist(self):
        """Integration: write_bootstrap_index requires run_dir to pre-exist."""
        with pytest.raises(FileNotFoundError):
            ba.write_bootstrap_index("/nonexistent/run/dir", {})

    def test_validate_non_dict(self):
        """TC-e: non-dict returns error."""
        errors = ba.validate_bootstrap_artifact("not a dict")
        assert len(errors) == 1
        assert "must be a dict" in errors[0]

    def test_validate_wrong_type(self):
        """TC-f: wrong type on a required field returns error."""
        artifact = {
            "engine": "gemini",
            "ok": "not_a_bool",  # wrong type
            "phase": "bootstrap",
            "authoritative": True,
            "resume_handle": "ok",
            "resume_kind": "ok",
            "source": "ok",
            "captured_at": "ok",
            "failure_reason": None,
        }
        errors = ba.validate_bootstrap_artifact(artifact)
        assert len(errors) >= 1
        assert any("ok" in e for e in errors)


# ══════════════════════════════════════════════════════════════════════════
# Invocation-scoped isolation
# ══════════════════════════════════════════════════════════════════════════

class TestInvocationScopedIsolation:
    """TC-17: artifacts are invocation-scoped, not shared / run-level."""

    def test_two_invocations_produce_two_files(self, run_dir):
        """TC-17: two invocation_ids → two distinct artefact files."""
        path_a = ba.write_bootstrap_success(
            run_dir=run_dir,
            invocation_id="inv_a",
            engine="gemini",
            resume_handle="h_a",
            resume_kind="session_id",
            source="cli_runtime",
            captured_at="2026-05-13T10:00:00+00:00",
        )
        path_b = ba.write_bootstrap_success(
            run_dir=run_dir,
            invocation_id="inv_b",
            engine="gemini",
            resume_handle="h_b",
            resume_kind="session_id",
            source="cli_runtime",
            captured_at="2026-05-13T10:01:00+00:00",
        )

        assert path_a != path_b
        assert os.path.exists(path_a)
        assert os.path.exists(path_b)

        a = ba.read_bootstrap_artifact(run_dir, "inv_a")
        b = ba.read_bootstrap_artifact(run_dir, "inv_b")
        assert a["resume_handle"] == "h_a"
        assert b["resume_handle"] == "h_b"


# ══════════════════════════════════════════════════════════════════════════
# agent_driver.py integration surface
# ══════════════════════════════════════════════════════════════════════════

class TestAgentDriverIntegration:
    """Verify the convenience wrappers added to agent_driver.py work correctly."""

    def test_ensure_bootstrap_dir_creates_directory(self, run_dir):
        """ensure_bootstrap_dir creates the directory and returns its path."""
        from agent_driver import ensure_bootstrap_dir
        path = ensure_bootstrap_dir(run_dir)
        assert path == os.path.join(run_dir, "bootstrap", "")
        assert os.path.isdir(path)

    def test_record_bootstrap_success_writes_artifact(self, run_dir):
        """record_bootstrap_success writes a valid artifact."""
        from agent_driver import record_bootstrap_success

        path = record_bootstrap_success(
            run_dir=run_dir,
            invocation_id="inv_001",
            engine="openclaw",
            resume_handle="sk_42",
            resume_kind="session_id",
        )
        assert os.path.exists(path)
        artifact = ba.read_bootstrap_artifact(run_dir, "inv_001")
        assert artifact["ok"] is True
        assert artifact["authoritative"] is True

    def test_record_bootstrap_failure_writes_artifact(self, run_dir):
        """record_bootstrap_failure writes a valid artifact."""
        from agent_driver import record_bootstrap_failure

        path = record_bootstrap_failure(
            run_dir=run_dir,
            invocation_id="inv_001",
            engine="gemini",
            failure_reason="missing_authoritative_resume_handle",
        )
        assert os.path.exists(path)
        artifact = ba.read_bootstrap_artifact(run_dir, "inv_001")
        assert artifact["ok"] is False
        assert artifact["authoritative"] is False

    def test_record_bootstrap_index_writes_index(self, run_dir):
        """record_bootstrap_index writes a valid index artifact."""
        from agent_driver import record_bootstrap_index

        path = record_bootstrap_index(
            run_dir,
            {"planner": "bootstrap/inv_001.json"},
        )
        assert os.path.exists(path)
        index = ba.read_bootstrap_index(run_dir)
        assert index["active_targets"]["planner"] == "bootstrap/inv_001.json"

    def test_is_eligible_for_strong_continuity_true(self, run_dir):
        """is_eligible_for_strong_continuity returns True for a success artifact."""
        from agent_driver import (
            record_bootstrap_success,
            is_eligible_for_strong_continuity,
        )
        record_bootstrap_success(
            run_dir=run_dir,
            invocation_id="inv_001",
            engine="openclaw",
            resume_handle="sk_42",
            resume_kind="session_id",
        )
        assert is_eligible_for_strong_continuity(run_dir, "inv_001") is True

    def test_is_eligible_for_strong_continuity_false_for_failure(self, run_dir):
        """is_eligible_for_strong_continuity returns False for a failure artifact."""
        from agent_driver import (
            record_bootstrap_failure,
            is_eligible_for_strong_continuity,
        )
        record_bootstrap_failure(
            run_dir=run_dir,
            invocation_id="inv_001",
            engine="gemini",
        )
        assert is_eligible_for_strong_continuity(run_dir, "inv_001") is False

    def test_is_eligible_for_strong_continuity_false_for_missing(self, run_dir):
        """is_eligible_for_strong_continuity returns False when no artifact exists."""
        from agent_driver import is_eligible_for_strong_continuity
        assert is_eligible_for_strong_continuity(run_dir, "nonexistent") is False
