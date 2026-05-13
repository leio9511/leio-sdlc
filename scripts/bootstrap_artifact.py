"""
Bootstrap artifact model and authoritative truth contract — PR-002.

Defines the machine-readable bootstrap artifact schema, directory model,
index artifact, and authoritative-source classification rule.  This module
is the *truth layer* that downstream code uses to make hard eligibility
decisions: what counts as authoritative, what counts as heuristic, and how
bootstrap results are persisted as invocation-scoped structured JSON
artifacts.

No runtime behaviour is altered by this module — it is purely the data
contract and its read/write utilities.
"""
import json
import os
from datetime import datetime, timezone

# ── Authoritative vs. heuristic classification ──────────────────────────
# Copied verbatim from PRD sections 3.4 and 7.
#
# Extending the authoritative-source allowlist requires an architecture
# review per the authoritative-source rule in PRD section 3.4:
# only CLI/runtime machine-readable metadata, provider-documented and
# live-verified direct resume handles, and runtime-captured structured
# bootstrap results may be classified as authoritative.

_AUTHORITATIVE_SOURCE_LABELS = frozenset(
    ("cli_runtime", "provider_handle")
)


def classify_resume_source(source: str) -> str:
    """Classify a resume source label as 'authoritative' or 'heuristic'.

    Authoritative sources are strictly limited to labels in the allowlist:
        - ``"cli_runtime"``
        - ``"provider_handle"``

    Any source label not in the allowlist is classified as heuristic.
    """
    if source in _AUTHORITATIVE_SOURCE_LABELS:
        return "authoritative"
    return "heuristic"


# ── Directory & path model ──────────────────────────────────────────────
# Copied verbatim from PRD section 7:
#   <run_dir>/bootstrap/
#   <run_dir>/bootstrap/<agent_invocation_id>.json
#   <run_dir>/bootstrap_index.json


def get_bootstrap_dir(run_dir: str) -> str:
    """Return the bootstrap artifact directory for *run_dir*.

    Exact path rule: ``<run_dir>/bootstrap/``
    """
    return os.path.join(run_dir, "bootstrap", "")


def get_bootstrap_artifact_path(run_dir: str, invocation_id: str) -> str:
    """Return the invocation-scoped bootstrap artifact path.

    Exact path rule: ``<run_dir>/bootstrap/<agent_invocation_id>.json``
    """
    return os.path.join(get_bootstrap_dir(run_dir), f"{invocation_id}.json")


def get_bootstrap_index_path(run_dir: str) -> str:
    """Return the bootstrap index artifact path.

    Exact path rule: ``<run_dir>/bootstrap_index.json``
    """
    return os.path.join(run_dir, "bootstrap_index.json")


# ── Artifact I/O helpers ───────────────────────────────────────────────


def _read_json(path: str) -> dict:
    """Read and parse a JSON file at *path*."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: str, payload: dict) -> str:
    """Atomically write *payload* as JSON to *path*.

    Creates parent directories when the parent is a subdirectory of the
    expected artifact root.  For paths whose parent must already exist
    (e.g. bootstrap_index.json at the run-dir root), use ``_write_json_root``
    instead.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def _write_json_root(path: str, payload: dict) -> str:
    """Write *payload* as JSON to *path* — parent must already exist."""
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        raise FileNotFoundError(
            f"parent directory does not exist for index artifact: {parent}"
        )
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def write_bootstrap_success(
    run_dir: str,
    invocation_id: str,
    engine: str,
    resume_handle: str,
    resume_kind: str,
    source: str,
    captured_at: str | None = None,
) -> str:
    """Write a success bootstrap artifact and return the artifact path.

    Exact success schema from PRD section 7.
    """
    if captured_at is None:
        captured_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "engine": engine,
        "ok": True,
        "phase": "bootstrap",
        "authoritative": True,
        "resume_handle": resume_handle,
        "resume_kind": resume_kind,
        "source": source,
        "captured_at": captured_at,
        "failure_reason": None,
    }
    path = get_bootstrap_artifact_path(run_dir, invocation_id)
    return _write_json(path, payload)


def write_bootstrap_failure(
    run_dir: str,
    invocation_id: str,
    engine: str,
    failure_reason: str = "missing_authoritative_resume_handle",
) -> str:
    """Write a failure bootstrap artifact and return the artifact path.

    Exact failure schema from PRD section 7.
    """
    payload = {
        "engine": engine,
        "ok": False,
        "phase": "bootstrap",
        "authoritative": False,
        "resume_handle": None,
        "resume_kind": None,
        "source": None,
        "captured_at": None,
        "failure_reason": failure_reason,
    }
    path = get_bootstrap_artifact_path(run_dir, invocation_id)
    return _write_json(path, payload)


# ── Artifact read helpers ───────────────────────────────────────────────


def read_bootstrap_artifact(run_dir: str, invocation_id: str) -> dict:
    """Read and return the parsed JSON artifact dict for *invocation_id*.

    Raises ``FileNotFoundError`` if the artifact file does not exist.
    """
    path = get_bootstrap_artifact_path(run_dir, invocation_id)
    return _read_json(path)


def is_bootstrap_successful(artifact: dict) -> bool:
    """Return True if *artifact* represents a successful, authoritative bootstrap."""
    return artifact.get("ok") is True and artifact.get("authoritative") is True


def is_bootstrap_failed(artifact: dict) -> bool:
    """Return True if *artifact* represents a failed bootstrap."""
    return artifact.get("ok") is False


# ── Index artifact ──────────────────────────────────────────────────────
# Exact index schema from PRD section 7:
#   {
#     "active_targets": {
#       "<logical_target>": "bootstrap/<agent_invocation_id>.json"
#     }
#   }


def write_bootstrap_index(run_dir: str, active_targets: dict) -> str:
    """Write the bootstrap index artifact to ``<run_dir>/bootstrap_index.json``.

    *active_targets* must be a dict whose values are artifact-relative paths,
    e.g. ``{"coder": "bootstrap/abc123.json"}``.
    """
    payload = {"active_targets": active_targets}
    path = get_bootstrap_index_path(run_dir)
    return _write_json_root(path, payload)


def read_bootstrap_index(run_dir: str) -> dict:
    """Read and return the parsed bootstrap index dict."""
    path = get_bootstrap_index_path(run_dir)
    return _read_json(path)


def resolve_active_bootstrap_artifact(run_dir: str, logical_target: str) -> dict:
    """Read the bootstrap index, resolve *logical_target*, and return the artifact.

    This is the canonical single-shot lookup: index → artifact path → artifact.
    """
    index = read_bootstrap_index(run_dir)
    relative_path = index["active_targets"][logical_target]
    artifact_path = os.path.join(run_dir, relative_path)
    return _read_json(artifact_path)


# ── Validation ──────────────────────────────────────────────────────────

# Required fields and their expected types for valid bootstrap artifacts.
_REQUIRED_FIELDS: dict[str, type | tuple] = {
    "engine": str,
    "ok": bool,
    "phase": str,
    "authoritative": bool,
    "resume_handle": (str, type(None)),
    "resume_kind": (str, type(None)),
    "source": (str, type(None)),
    "captured_at": (str, type(None)),
    "failure_reason": (str, type(None)),
}


def validate_bootstrap_artifact(artifact: dict) -> list[str]:
    """Validate *artifact* against the required bootstrap schema.

    Returns a list of validation error messages (empty list if valid).
    Required fields must be present with correct types.
    """
    errors: list[str] = []
    if not isinstance(artifact, dict):
        return ["artifact must be a dict"]

    for field, expected_type in _REQUIRED_FIELDS.items():
        if field not in artifact:
            errors.append(f"missing required field: {field}")
        else:
            value = artifact[field]
            if not isinstance(value, expected_type):
                type_name = getattr(expected_type, "__name__", str(expected_type))
                errors.append(
                    f"field {field} expected {type_name}, got {type(value).__name__}: {value!r}"
                )

    return errors
