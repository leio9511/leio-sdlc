from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = REPO_ROOT / "docs" / "ci" / "preflight-soft-gate.md"
DEFAULT_PREFLIGHT_COMMAND = "bash preflight.sh"
REPORT_ALL_PREFLIGHT_COMMAND = "bash preflight.sh --report-all"
SINGLE_GATE_PRINCIPLE = (
    "fail-fast and report-all must execute the same repository preflight gate. "
    "they may differ only in stopping behavior and output aggregation."
)
TRUTHFUL_FAILURE_REQUIREMENT = (
    "if any preflight check fails, both fail-fast and report-all modes must exit non-zero. "
    "report-all must never convert a failing preflight run into success."
)


def _read_doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_preflight_soft_gate_doc_exists_at_expected_path():
    assert DOC_PATH.is_file()
    assert str(DOC_PATH.relative_to(REPO_ROOT)) == "docs/ci/preflight-soft-gate.md"


def test_preflight_soft_gate_doc_describes_layered_acceptance():
    content = _read_doc().lower()

    assert "layer a" in content
    assert "local contract validation" in content
    assert ".github/workflows/preflight.yml" in content

    assert "layer b" in content
    assert "local behavior" in content
    assert "semantics validation" in content
    assert DEFAULT_PREFLIGHT_COMMAND in content
    assert REPORT_ALL_PREFLIGHT_COMMAND in content
    assert "exit 0 -> ci job success" in content
    assert "non-zero exit -> ci job failure" in content

    assert "layer c" in content
    assert "external github witness" in content


def test_preflight_soft_gate_doc_describes_single_gate_dual_mode_contract():
    content = _read_doc().lower()

    assert "one real gate" in content
    assert "default fail-fast local and agent usage" in content
    assert "explicit report-all github ci usage" in content
    assert DEFAULT_PREFLIGHT_COMMAND in content
    assert REPORT_ALL_PREFLIGHT_COMMAND in content
    assert SINGLE_GATE_PRINCIPLE in content
    assert TRUTHFUL_FAILURE_REQUIREMENT in content


def test_preflight_soft_gate_doc_marks_external_witness_as_manual_post_sdlc():
    content = _read_doc().lower()

    assert "manual and post-sdlc" in content or "manual verification step after sdlc completion" in content
    assert "not part of the automated coder, reviewer, or uat closed loop" in content



def test_preflight_soft_gate_doc_records_required_manual_witness_fields():
    content = _read_doc().lower()

    required_fields = [
        "workflow name",
        "workflow path",
        "trigger event",
        "head sha",
        "run url or run id",
        "terminal conclusion",
        "timestamp",
    ]

    for field in required_fields:
        assert field in content
