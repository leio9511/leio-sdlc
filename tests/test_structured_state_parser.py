import pytest
import os
import sys

# Ensure scripts directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import structured_state_parser

def test_parse_valid_status_open(tmp_path):
    # Test Case 1: test_parse_valid_status_open
    file_path = tmp_path / "valid.md"
    file_path.write_text("---\nstatus: open\n---\nBody", encoding="utf-8")
    assert structured_state_parser.get_status(str(file_path)) == "open"

def test_parse_invalid_frontmatter(tmp_path):
    # Test Case 2: test_parse_invalid_frontmatter
    file_path = tmp_path / "invalid.md"
    file_path.write_text("status: open\nBody without dashes", encoding="utf-8")
    with pytest.raises(ValueError, match="No valid YAML frontmatter found"):
        structured_state_parser.get_status(str(file_path))

def test_update_status_preserves_content(tmp_path):
    # Test Case 3: test_update_status_preserves_content
    file_path = tmp_path / "preserve.md"
    original_content = "---\nstatus: open\nother_meta: test\n---\n# Header\nBody with status: closed\n"
    file_path.write_text(original_content, encoding="utf-8")
    
    structured_state_parser.update_status(str(file_path), "in_progress")
    
    updated_content = file_path.read_text(encoding="utf-8")
    expected_content = "---\nstatus: in_progress\nother_meta: test\n---\n# Header\nBody with status: closed\n"
    assert updated_content == expected_content

def test_get_next_pr_integration(tmp_path, monkeypatch):
    # Test Case 4: test_get_next_pr_integration
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    
    file1 = job_dir / "01_pr.md"
    file1.write_text("---\nstatus: closed\n---\nBody", encoding="utf-8")
    
    file2 = job_dir / "02_pr.md"
    file2.write_text("---\nstatus: open\n---\nBody", encoding="utf-8")
    
    file3 = job_dir / "03_pr.md"
    file3.write_text("---\nstatus: in_progress\n---\nBody", encoding="utf-8")

    # Import get_next_pr to test it
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
    import get_next_pr

    # Use monkeypatch to simulate command line args
    monkeypatch.setattr("sys.argv", ["get_next_pr.py", "--workdir", str(tmp_path), "--job-dir", str(job_dir)])
    
    # Capture standard output and sys.exit code
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
