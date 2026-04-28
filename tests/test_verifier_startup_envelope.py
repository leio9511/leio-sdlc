import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

from envelope_assembler import (
    build_startup_envelope,
    render_envelope_to_prompt,
    save_envelope_artifacts,
)


class TestVerifierStartupEnvelope(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_schema = {
            "status": "(PASS|NEEDS_FIX)",
            "verification_details": [
                {
                    "requirement": "string",
                    "status": "(IMPLEMENTED|MISSING|PARTIAL)",
                    "evidence": "string",
                    "comments": "string",
                }
            ],
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def build_envelope(self, prd_file="/tmp/PRD_A.md,/tmp/PRD_B.md"):
        return build_startup_envelope(
            role="verifier",
            workdir="/tmp/workdir",
            out_dir=self.temp_dir,
            references={
                "prd_file": prd_file,
                "playbook_path": "/tmp/playbooks/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/tmp/workdir/uat_report.json",
                "output_schema": self.output_schema,
            },
        )

    def test_verifier_envelope_shape(self):
        envelope = self.build_envelope()

        self.assertEqual(envelope["role"], "verifier")
        self.assertEqual(set(envelope.keys()), {"role", "execution_contract", "reference_index", "final_checklist"})
        contract_text = "\n".join(envelope["execution_contract"])
        self.assertIn("Read-Only (EMPHASIZED)", contract_text)
        self.assertIn("output_file", contract_text)
        self.assertIn("Required JSON Schema", contract_text)
        self.assertIn(json.dumps(self.output_schema, indent=2), contract_text)

    def test_verifier_multi_prd_parsing(self):
        envelope = self.build_envelope("PRD_A.md, PRD_B.md")
        prd_refs = [ref for ref in envelope["reference_index"] if ref["kind"] == "prd"]

        self.assertEqual([ref["path"] for ref in prd_refs], ["PRD_A.md", "PRD_B.md"])
        self.assertEqual([ref["id"] for ref in prd_refs], ["prd_1", "prd_2"])
        self.assertTrue(all(ref["required"] for ref in prd_refs))
        self.assertTrue(all(ref["priority"] == 1 for ref in prd_refs))

    def test_verifier_prompt_rendering(self):
        envelope = self.build_envelope("/tmp/PRD_A.md,/tmp/PRD_B.md")
        prompt = render_envelope_to_prompt(envelope)

        self.assertTrue(prompt.startswith("# EXECUTION CONTRACT"))
        self.assertIn("# REFERENCE INDEX", prompt)
        self.assertIn("/tmp/playbooks/verifier_playbook.md", prompt)
        self.assertIn("/tmp/PRD_A.md", prompt)
        self.assertIn("/tmp/PRD_B.md", prompt)
        self.assertIn("Read-Only (EMPHASIZED)", prompt)
        self.assertIn("output_file", prompt)
        self.assertNotIn("--- VERIFIER PLAYBOOK ---", prompt)
        self.assertNotIn("You are an independent, read-only QA Engine", prompt)

    def test_verifier_artifact_subdir(self):
        envelope = self.build_envelope()
        prompt = render_envelope_to_prompt(envelope)

        debug_dir = save_envelope_artifacts(
            role="verifier",
            out_dir=self.temp_dir,
            envelope=envelope,
            rendered_prompt=prompt,
            artifact_subdir="initial",
        )

        self.assertEqual(debug_dir, os.path.join(self.temp_dir, "verifier_debug", "initial"))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_packet.json")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "rendered_prompt.txt")))

    @patch('utils_api_key.setup_spawner_api_key')
    def test_spawn_verifier_saves_uat_initial_artifacts_in_test_mode(self, mock_setup_key):
        import spawn_verifier

        prd_a = os.path.join(self.temp_dir, "PRD_A.md")
        prd_b = os.path.join(self.temp_dir, "PRD_B.md")
        out_file = os.path.join(self.temp_dir, "uat_report.json")
        with open(prd_a, "w") as f:
            f.write("# PRD A")
        with open(prd_b, "w") as f:
            f.write("# PRD B")

        test_args = [
            "spawn_verifier.py",
            "--prd-files",
            f"{prd_a},{prd_b}",
            "--workdir",
            self.temp_dir,
            "--out-file",
            out_file,
            "--enable-exec-from-workspace",
        ]

        with patch.object(sys, 'argv', test_args):
            with patch.dict(os.environ, {"SDLC_TEST_MODE": "true", "SDLC_RUN_DIR": self.temp_dir}, clear=False):
                spawn_verifier.main()

        debug_dir = os.path.join(self.temp_dir, "uat_debug", "initial")
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "startup_packet.json")))
        self.assertTrue(os.path.exists(os.path.join(debug_dir, "rendered_prompt.txt")))
        self.assertTrue(os.path.exists(out_file))

        with open(os.path.join(debug_dir, "startup_packet.json")) as f:
            packet = json.load(f)
        self.assertEqual(packet["role"], "verifier")
        self.assertEqual(
            [ref["path"] for ref in packet["reference_index"] if ref["kind"] == "prd"],
            [prd_a, prd_b],
        )

        with open(os.path.join(debug_dir, "rendered_prompt.txt")) as f:
            rendered = f.read()
        self.assertIn("# EXECUTION CONTRACT", rendered)
        self.assertIn("verifier_playbook.md", rendered)


if __name__ == '__main__':
    unittest.main()
