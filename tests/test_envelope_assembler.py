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
        envelope = build_startup_envelope(
            role="reviewer",
            workdir="/test/workdir",
            out_dir="/test/out_dir",
            references={
                "prd_file": "/test/prd.md",
                "pr_contract_file": "/test/pr.md",
                "diff_file": "/test/diff.diff",
                "playbook_path": "/test/playbook.md",
            },
            contract_params={
                "output_file": "/test/out.json",
                "output_schema": {"status": "string"},
            },
        )
        self.assertEqual(envelope["role"], "reviewer")
        self.assertIn("execution_contract", envelope)
        self.assertIn("reference_index", envelope)
        self.assertIn("final_checklist", envelope)

    def test_build_coder_initial_startup_envelope(self):
        envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/PR_001.md",
                "prd_file": "/test/PRD.md",
                "playbook_path": "/test/coder_playbook.md",
            },
            contract_params={},
            mode="initial",
        )

        self.assertEqual(envelope["role"], "coder")
        self.assertEqual(set(envelope.keys()), {"role", "execution_contract", "reference_index", "final_checklist"})

        refs_by_id = {ref["id"]: ref for ref in envelope["reference_index"]}
        self.assertEqual(refs_by_id["pr_contract"]["path"], "/test/PR_001.md")
        self.assertEqual(refs_by_id["prd"]["path"], "/test/PRD.md")
        self.assertEqual(refs_by_id["coder_playbook"]["path"], "/test/coder_playbook.md")
        self.assertTrue(all(ref["required"] for ref in refs_by_id.values()))
        self.assertTrue(all(ref["priority"] == 1 for ref in refs_by_id.values()))

    def test_build_verifier_startup_envelope(self):
        envelope = build_startup_envelope(
            role="verifier",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "prd_files": "PRD_1.md, PRD_2.md",
                "playbook_path": "/test/playbooks/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/test/workdir/uat_report.json",
            },
        )

        self.assertEqual(envelope["role"], "verifier")
        self.assertEqual(len([ref for ref in envelope["reference_index"] if ref["kind"] == "prd"]), 2)

        # Verify specific verifier contract clauses
        contract_text = "\n".join(envelope["execution_contract"])
        self.assertIn("Read-Only (EMPHASIZED)", contract_text)
        self.assertIn("output_file: `/test/workdir/uat_report.json`", contract_text)

    def test_rendered_coder_prompt_is_contract_first_and_path_driven(self):
        envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/contracts/PR_001.md",
                "prd_file": "/test/docs/PRD.md",
                "playbook_path": "/test/playbooks/coder_playbook.md",
            },
            contract_params={},
            mode="initial",
        )

        prompt = render_envelope_to_prompt(envelope)

        self.assertTrue(prompt.startswith("# EXECUTION CONTRACT"))
        self.assertIn("/test/contracts/PR_001.md", prompt)
        self.assertIn("/test/docs/PRD.md", prompt)
        self.assertIn("/test/playbooks/coder_playbook.md", prompt)
        self.assertNotIn("--- PR Contract", prompt)
        self.assertNotIn("--- PRD", prompt)
        self.assertNotIn("--- CODER PLAYBOOK ---", prompt)

    def test_render_envelope_to_prompt(self):
        envelope = {
            "execution_contract": ["A clause"],
            "reference_index": [{"id": "1", "kind": "test"}],
            "final_checklist": ["Check 1"],
        }
        prompt = render_envelope_to_prompt(envelope)
        self.assertIn("# EXECUTION CONTRACT", prompt)
        self.assertIn("# REFERENCE INDEX", prompt)
        self.assertIn("# FINAL CHECKLIST", prompt)

    def test_save_envelope_artifacts(self):
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

    def test_save_coder_envelope_artifacts_supports_mode_scoped_paths(self):
        envelope = {
            "role": "coder",
            "execution_contract": ["clause"],
            "reference_index": [],
            "final_checklist": ["done"],
        }
        prompt = "# EXECUTION CONTRACT\n- clause"

        debug_dir = save_envelope_artifacts(
            "coder",
            self.temp_dir,
            envelope,
            prompt,
            artifact_subdir="initial",
        )

        self.assertEqual(debug_dir, os.path.join(self.temp_dir, "coder_debug", "initial"))

        with open(os.path.join(debug_dir, "startup_packet.json"), "r") as f:
            data = json.load(f)
            self.assertEqual(data["role"], "coder")

        with open(os.path.join(debug_dir, "rendered_prompt.txt"), "r") as f:
            text = f.read()
            self.assertEqual(text, prompt)

    def test_planner_backward_compatibility(self):
        import planner_envelope as pe

        envelope = pe.build_planner_envelope(
            workdir="/workdir",
            out_dir=self.temp_dir,
            prd_path="/prd.md",
            playbook_path="/playbook.md",
            template_path="/template.md",
            contract_script="/script.py",
        )

        self.assertEqual(envelope["role"], "planner")

        prompt = pe.render_planner_prompt(envelope)
        self.assertIn("# EXECUTION CONTRACT", prompt)

        pe.save_debug_artifacts(
            out_dir=self.temp_dir,
            envelope_dict=envelope,
            rendered_prompt=prompt,
            scaffold_command="scaffold command",
        )

        debug_dir = os.path.join(self.temp_dir, "planner_debug")
        self.assertTrue(os.path.isdir(debug_dir))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_prompt.txt")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "scaffold_contract.txt")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_packet.json")))


if __name__ == '__main__':
    unittest.main()
