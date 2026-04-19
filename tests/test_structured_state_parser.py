import pytest
import os
import sys
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import structured_state_parser

def test_parser_extracts_status_with_pyyaml(tmp_path):
    file_path = tmp_path / "valid.md"
    file_path.write_text("---\nstatus: open\n---\nBody", encoding="utf-8")
    assert structured_state_parser.get_status(str(file_path)) == "open"

def test_parser_error_no_boundary(tmp_path):
    file_path = tmp_path / "invalid.md"
    file_path.write_text("status: open\nBody without dashes", encoding="utf-8")
    expected_msg = re.escape(f"[FATAL_FORMAT] No valid YAML frontmatter delimiters (---) found in file: {os.path.abspath(str(file_path))}")
    with pytest.raises(ValueError, match=expected_msg):
        structured_state_parser.get_status(str(file_path))

def test_parser_error_yaml_syntax(tmp_path):
    file_path = tmp_path / "invalid_yaml.md"
    file_path.write_text("---\nstatus: open\ninvalid: [yaml:\n---\nBody", encoding="utf-8")
    prefix = re.escape("[FATAL_FORMAT] YAML syntax error in frontmatter: ")
    suffix = re.escape(f" at {os.path.abspath(str(file_path))}")
    expected_msg = f"^{prefix}(?s:.*){suffix}$"
    with pytest.raises(ValueError, match=expected_msg):
        structured_state_parser.get_status(str(file_path))

def test_update_status_preserves_content(tmp_path):
    file_path = tmp_path / "preserve.md"
    original_content = "---\nstatus: open\nother_meta: test\n---\n# Header\nBody with status: closed\n"
    file_path.write_text(original_content, encoding="utf-8")
    structured_state_parser.update_status(str(file_path), "in_progress")
    updated_content = file_path.read_text(encoding="utf-8")
    expected_content = "---\nstatus: in_progress\nother_meta: test\n---\n# Header\nBody with status: closed\n"
    assert updated_content == expected_content

def test_get_next_pr_integration(tmp_path, monkeypatch):
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    file1 = job_dir / "01_pr.md"
    file1.write_text("---\nstatus: closed\n---\nBody", encoding="utf-8")
    file2 = job_dir / "02_pr.md"
    file2.write_text("---\nstatus: open\n---\nBody", encoding="utf-8")
    file3 = job_dir / "03_pr.md"
    file3.write_text("---\nstatus: in_progress\n---\nBody", encoding="utf-8")
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
    import get_next_pr
    monkeypatch.setattr("sys.argv", ["get_next_pr.py", "--workdir", str(tmp_path), "--job-dir", str(job_dir)])
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    exit_code = None
    with redirect_stdout(f):
        try:
            get_next_pr.main()
        except SystemExit as e:
            exit_code = e.code
    output = f.getvalue()
    assert str(file2) in output
    assert exit_code == 0
