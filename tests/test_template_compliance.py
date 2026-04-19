import os
import glob
import subprocess
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.structured_state_parser import get_status, VALID_STATES

def test_all_templates_compliant():
    templates = glob.glob('TEMPLATES/**/*.md.template', recursive=True)
    assert len(templates) > 0, "No templates found"
    for template in templates:
        status = get_status(template)
        assert status in VALID_STATES

def test_preflight_gate_execution():
    if os.environ.get("SKIP_PREFLIGHT_RECURSION"):
        pytest.skip("Avoiding infinite recursion")

    invalid_template = "TEMPLATES/invalid_test_template.md.template"
    with open(invalid_template, "w") as f:
        f.write("---\nstatus: invalid_status\n---\n")

    try:
        env = os.environ.copy()
        env["SKIP_PREFLIGHT_RECURSION"] = "1"
        result = subprocess.run(["bash", "./preflight.sh"], capture_output=True, env=env, text=True)
        assert result.returncode != 0, f"Expected preflight.sh to fail with invalid template. STDOUT: {result.stdout} STDERR: {result.stderr}"
        # Make sure the failure was due to the compliance check
        assert "Template Compliance Gate" in result.stdout or "invalid_status" in result.stdout or "FAILED" in result.stdout
    finally:
        if os.path.exists(invalid_template):
            os.remove(invalid_template)
