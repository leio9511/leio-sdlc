import pytest
import os
import glob
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import structured_state_parser

def test_template_compliance():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    templates_dir = os.path.join(project_root, 'TEMPLATES')
    
    template_files = glob.glob(os.path.join(templates_dir, '*.md.template'))
    
    assert len(template_files) > 0, f"No templates found in {templates_dir}"
    
    for file_path in template_files:
        try:
            status = structured_state_parser.get_status(file_path)
            assert status in structured_state_parser.VALID_STATES, f"Status '{status}' not in VALID_STATES for {file_path}"
        except Exception as e:
            pytest.fail(f"Template compliance failed for {file_path}: {str(e)}")

