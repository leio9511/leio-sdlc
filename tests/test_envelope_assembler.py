import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from envelope_assembler import (
    build_startup_envelope,
    render_envelope_to_prompt,
    save_envelope_artifacts,
)

class TestEnvelopeAssembler(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_build_startup_envelope(self):
        # QA Blueprint Test Case 1: test_build_startup_envelope
        envelope = build_startup_envelope(
            role="reviewer",
            workdir="/test/workdir",
            out_dir="/test/out_dir",
            references={
                "prd_file": "/test/prd.md",
                "pr_contract_file": "/test/pr.md",
                "diff_file": "/test/diff.diff",
                "playbook_path": "/test/playbook.md"
            },
            contract_params={
                "output_file": "/test/out.json",
                "output_schema": {"status": "string"}
            }
        )
        self.assertEqual(envelope["role"], "reviewer")
        self.assertIn("execution_contract", envelope)
        self.assertIn("reference_index", envelope)
        self.assertIn("final_checklist", envelope)

    def test_render_envelope_to_prompt(self):
        # QA Blueprint Test Case 2: test_render_envelope_to_prompt
        envelope = {
            "execution_contract": ["A clause"],
            "reference_index": [{"id": "1", "kind": "test"}],
            "final_checklist": ["Check 1"]
        }
        prompt = render_envelope_to_prompt(envelope)
        self.assertIn("# EXECUTION CONTRACT", prompt)
        self.assertIn("# REFERENCE INDEX", prompt)
        self.assertIn("# FINAL CHECKLIST", prompt)

    def test_save_envelope_artifacts(self):
        # QA Blueprint Test Case 3: test_save_envelope_artifacts
        envelope = {"role": "reviewer", "test": "data"}
        prompt = "test prompt"
        save_envelope_artifacts("reviewer", self.temp_dir, envelope, prompt)
        
        debug_dir = os.path.join(self.temp_dir, "reviewer_debug")
        self.assertTrue(os.path.isdir(debug_dir))
        
        with open(os.path.join(debug_dir, "startup_packet.json"), "r") as f:
            data = json.load(f)
            self.assertEqual(data["test"], "data")
            
        with open(os.path.join(debug_dir, "rendered_prompt.txt"), "r") as f:
            text = f.read()
            self.assertEqual(text, "test prompt")

    def test_planner_backward_compatibility(self):
        # QA Blueprint Test Case 4: test_planner_backward_compatibility
        # Uses planner_envelope adapter
        import planner_envelope as pe
        
        envelope = pe.build_planner_envelope(
            workdir="/workdir",
            out_dir=self.temp_dir,
            prd_path="/prd.md",
            playbook_path="/playbook.md",
            template_path="/template.md",
            contract_script="/script.py"
        )
        
        self.assertEqual(envelope["role"], "planner")
        
        prompt = pe.render_planner_prompt(envelope)
        self.assertIn("# EXECUTION CONTRACT", prompt)
        
        pe.save_debug_artifacts(
            out_dir=self.temp_dir,
            envelope_dict=envelope,
            rendered_prompt=prompt,
            scaffold_command="scaffold command"
        )
        
        debug_dir = os.path.join(self.temp_dir, "planner_debug")
        self.assertTrue(os.path.isdir(debug_dir))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_prompt.txt")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "scaffold_contract.txt")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_packet.json")))

if __name__ == '__main__':
    unittest.main()
