import os
import re

def test_template_has_yaml_boundaries():
    template_path = os.path.join(os.path.dirname(__file__), "..", "TEMPLATES", "PR_Contract.md.template")
    assert os.path.exists(template_path), f"File {template_path} does not exist"
    
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert content.startswith("---\n"), "Template does not start with YAML boundary"
    
    match = re.search(r"^---\n(.*?)\n---\n", content, re.MULTILINE | re.DOTALL)
    assert match is not None, "Template does not contain a closing YAML boundary"
    assert "status:" in match.group(1), "Template YAML frontmatter does not contain a status field"
