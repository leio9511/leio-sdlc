import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))

import pytest
from envelope_assembler import (
    build_startup_envelope,
    render_envelope_to_prompt,
    save_envelope_artifacts,
    ROLE_PROLOGUES,
    render_coder_v1_bootstrap_prompt,
)


ROLES = ["planner", "coder", "reviewer", "verifier", "auditor", "forensic"]

@pytest.fixture
def mock_params():
    return {
        "workdir": "/tmp/workdir",
        "out_dir": "/tmp/out_dir",
        "references": {
            "prd_file": "/tmp/prd.md",
            "playbook_path": "/tmp/playbook.md",
            "template_path": "/tmp/template.md",
            "diff_file": "/tmp/diff.patch",
            "pr_contract_file": "/tmp/pr.md",
            "prd_files": ["/tmp/prd1.md", "/tmp/prd2.md"],
        },
        "contract_params": {
            "scaffold_command": "scaffold.sh",
            "output_file": "/tmp/output.json",
            "output_schema": {"type": "object"}
        }
    }


def test_render_envelope_structure_and_sections(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        # If build_startup_envelope doesn't explicitly support forensic, it returns empty lists. We must manually set role.
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        assert "## IDENTITY & PRIMARY GOAL" in prompt
        # Wait, if a role has no constraints, we might not output OPERATING CONSTRAINTS in the current implementation.
        # But wait, forensic doesn't generate ANY constraints, so it won't have OPERATING CONSTRAINTS.
        # Let's check if the test requires it for ALL roles or if the implementation should just output it unconditionally.
        # "Asserts the presence of the exact section headers: IDENTITY, OPERATING CONSTRAINTS, START WORK"
        # I'll update the implementation to ALWAYS output the OPERATING CONSTRAINTS section.
        assert "## OPERATING CONSTRAINTS" in prompt, f"Missing OPERATING CONSTRAINTS for {role}"
        assert "## START WORK" in prompt


def test_render_envelope_preserves_execution_contract(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        for clause in envelope.get("execution_contract", []):
            assert clause in prompt, f"Missing clause in {role}: {clause}"


def test_render_envelope_preserves_references(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        expected_json = json.dumps(envelope.get("reference_index", []), indent=2)
        assert expected_json in prompt, f"Missing reference index for {role}"


def test_render_envelope_cta_last_section(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        sections = prompt.split("## ")
        last_section = "## " + sections[-1]
        
        assert last_section.startswith("## START WORK")
        assert f"As the {role.upper()}" in last_section


def test_render_envelope_role_prologues(mock_params):
    for role in ROLES:
        envelope = build_startup_envelope(
            role, 
            mock_params["workdir"], 
            mock_params["out_dir"], 
            mock_params["references"], 
            mock_params["contract_params"]
        )
        envelope["role"] = role
        prompt = render_envelope_to_prompt(envelope)
        
        expected_prologue = ROLE_PROLOGUES[role]
        assert expected_prologue in prompt


class TestEnvelopeAssembler(unittest.TestCase):
    REVIEWER_EVIDENCE_ONLY_BOUNDARY_RULES = [
        "Do not run repository tests.",
        "Do not trigger approval-requiring commands.",
        "If evidence is insufficient, report insufficient evidence instead of executing tests yourself.",
    ]
    VERIFIER_EVIDENCE_ONLY_BOUNDARY_RULES = [
        "Do not run repository tests.",
        "Do not trigger approval-requiring commands.",
        "If evidence is insufficient, report insufficient evidence instead of executing tests yourself.",
    ]

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

    def test_reviewer_envelope_includes_evidence_only_boundary_rules(self):
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

        execution_contract = envelope["execution_contract"]
        for rule in self.REVIEWER_EVIDENCE_ONLY_BOUNDARY_RULES:
            self.assertIn(rule, execution_contract)

        prompt = render_envelope_to_prompt(envelope)
        self.assertIn("## EXECUTION CONTRACT", prompt)
        for rule in self.REVIEWER_EVIDENCE_ONLY_BOUNDARY_RULES:
            self.assertIn(rule, prompt)

    def test_v2_new_session_prompts_report_single_assembly_authority_without_spawn_coder_owned_prompt_bodies(self):
        playbook_path = os.path.join(self.temp_dir, "coder_playbook_v2.md")
        feedback_path = os.path.join(self.temp_dir, "review.json")
        with open(playbook_path, "w", encoding="utf-8") as f:
            f.write("# Coder Playbook V2\n\nUse Red → Green → Refactor.\n")
        with open(feedback_path, "w", encoding="utf-8") as f:
            f.write('{"status": "NEEDS_FIX"}')

        scenarios = [
            (
                "initial_v2",
                {},
                {
                    "mode": "initial",
                    "scenario_type": "initial",
                    "startup_version": "v2",
                    "coder_playbook_version": 2,
                    "lifecycle": "new_session_startup",
                    "prompt_kind": "coder_initial_v2_startup",
                },
            ),
            (
                "revision_bootstrap_v2",
                {"current_branch": "feature/test", "latest_commit_hash": "abc123"},
                {
                    "mode": "revision_bootstrap",
                    "scenario_type": "revision_bootstrap",
                    "startup_version": "v2",
                    "coder_playbook_version": 2,
                    "lifecycle": "recovery_bootstrap_startup",
                    "prompt_kind": "coder_revision_bootstrap_v2_startup",
                },
            ),
            (
                "system_alert_bootstrap_v2",
                {"system_alert": "git dirty", "current_branch": "feature/test", "latest_commit_hash": "abc123"},
                {
                    "mode": "system_alert_bootstrap",
                    "scenario_type": "system_alert_bootstrap",
                    "startup_version": "v2",
                    "coder_playbook_version": 2,
                    "lifecycle": "recovery_bootstrap_startup",
                    "prompt_kind": "coder_system_alert_bootstrap_v2_startup",
                },
            ),
        ]

        for mode, contract_params, expected in scenarios:
            references = {
                "pr_contract_file": "/test/contracts/PR_001.md",
                "prd_file": "/test/docs/PRD.md",
                "playbook_path": playbook_path,
            }
            if mode == "revision_bootstrap_v2":
                references["feedback_file"] = feedback_path

            envelope = build_startup_envelope(
                role="coder",
                workdir="/test/workdir",
                out_dir="/test/run_dir",
                references=references,
                contract_params=contract_params,
                mode=mode,
            )
            prompt = render_envelope_to_prompt(envelope)

            self.assertEqual(envelope["assembly_authority_path"], "scripts/envelope_assembler.py")
            for key, value in expected.items():
                self.assertEqual(envelope[key], value)
            self.assertIn("## CODER PLAYBOOK", prompt)
            self.assertIn("# Coder Playbook V2", prompt)
            self.assertIn("Use Red → Green → Refactor.", prompt)
            self.assertNotIn("spawn_coder.py", prompt)

    def test_v1_bootstrap_prompts_render_from_envelope_assembler_with_matching_authority_metadata(self):
        feedback_path = os.path.join(self.temp_dir, "review.json")
        with open(feedback_path, "w", encoding="utf-8") as f:
            f.write('{"status": "NEEDS_FIX", "comments": "restore via v1"}')

        revision_envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/contracts/PR_001.md",
                "prd_file": "/test/docs/PRD.md",
                "playbook_path": "/test/playbooks/coder_playbook.md",
                "feedback_file": feedback_path,
            },
            contract_params={
                "current_branch": "feature/test",
                "latest_commit_hash": "abc123",
            },
            mode="revision_bootstrap",
        )
        revision_prompt = render_envelope_to_prompt(revision_envelope)
        self.assertEqual(revision_envelope["assembly_authority_path"], "scripts/envelope_assembler.py")
        self.assertEqual(revision_envelope["startup_version"], "v1")
        self.assertIn("# CODER REVISION RECOVERY CONTINUATION", revision_prompt)
        self.assertIn("# REVIEW REPORT JSON", revision_prompt)
        self.assertIn("restore via v1", revision_prompt)
        self.assertEqual(revision_prompt, render_coder_v1_bootstrap_prompt(revision_envelope))

        alert_envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/contracts/PR_001.md",
                "prd_file": "/test/docs/PRD.md",
                "playbook_path": "/test/playbooks/coder_playbook.md",
            },
            contract_params={
                "system_alert": "git dirty",
                "current_branch": "feature/test",
                "latest_commit_hash": "abc123",
            },
            mode="system_alert_bootstrap",
        )
        alert_prompt = render_envelope_to_prompt(alert_envelope)
        self.assertEqual(alert_envelope["assembly_authority_path"], "scripts/envelope_assembler.py")
        self.assertEqual(alert_envelope["startup_version"], "v1")
        self.assertIn("# CODER SYSTEM ALERT RECOVERY CONTINUATION", alert_prompt)
        self.assertIn("# SYSTEM ALERT YOU MUST FIX", alert_prompt)
        self.assertIn("git dirty", alert_prompt)
        self.assertEqual(alert_prompt, render_coder_v1_bootstrap_prompt(alert_envelope))

    def test_build_coder_initial_v2_envelope_keeps_thin_shell_and_removes_playbook_from_required_refs(self):
        playbook_path = os.path.join(self.temp_dir, "coder_playbook_v2.md")
        with open(playbook_path, "w", encoding="utf-8") as f:
            f.write("# Coder Playbook V2\n\nUse Red → Green → Refactor.\n")

        envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/PR_001.md",
                "prd_file": "/test/PRD.md",
                "playbook_path": playbook_path,
            },
            contract_params={},
            mode="initial_v2",
        )

        self.assertEqual(envelope["role"], "coder")
        self.assertEqual(envelope["startup_version"], "v2")
        self.assertEqual(envelope["coder_playbook_version"], 2)
        self.assertEqual(envelope["scenario_type"], "initial")
        self.assertEqual(envelope["mode"], "initial")
        self.assertEqual(envelope["lifecycle"], "new_session_startup")
        self.assertEqual(envelope["assembly_authority_path"], "scripts/envelope_assembler.py")
        self.assertIn("immediately", envelope["mission"])
        self.assertIn("# Coder Playbook V2", envelope["inline_playbook"]["content"])
        self.assertEqual([ref["id"] for ref in envelope["reference_index"]], ["pr_contract", "prd"])
        self.assertNotIn("coder_playbook", [ref["id"] for ref in envelope["reference_index"]])

        prompt = render_envelope_to_prompt(envelope)
        self.assertIn("## MISSION", prompt)
        self.assertIn("## CODER PLAYBOOK", prompt)
        self.assertIn("# Coder Playbook V2", prompt)
        self.assertIn("/test/PR_001.md", prompt)
        self.assertIn("/test/PRD.md", prompt)
        self.assertNotIn("coder_playbook_v2.md", json.dumps(envelope["reference_index"]))
        self.assertNotIn("## EXECUTION CONTRACT", prompt)
        self.assertNotIn("## FINAL CHECKLIST", prompt)

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
        self.assertEqual(envelope["mode"], "initial")
        self.assertEqual(envelope["scenario_type"], "initial")
        self.assertEqual(envelope["startup_version"], "v1")
        self.assertEqual(envelope["coder_playbook_version"], 1)
        self.assertEqual(envelope["assembly_authority_path"], "scripts/envelope_assembler.py")
        self.assertEqual(envelope["lifecycle"], "new_session_startup")
        self.assertEqual(envelope["prompt_kind"], "coder_initial_startup")
        self.assertIn("execution_contract", envelope)
        self.assertIn("reference_index", envelope)
        self.assertIn("final_checklist", envelope)

        refs_by_id = {ref["id"]: ref for ref in envelope["reference_index"]}
        self.assertEqual(refs_by_id["pr_contract"]["path"], "/test/PR_001.md")
        self.assertEqual(refs_by_id["prd"]["path"], "/test/PRD.md")
        self.assertEqual(refs_by_id["coder_playbook"]["path"], "/test/coder_playbook.md")
        self.assertTrue(all(ref["required"] for ref in refs_by_id.values()))
        self.assertTrue(all(ref["priority"] == 1 for ref in refs_by_id.values()))

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

        self.assertIn("## EXECUTION CONTRACT", prompt)
        self.assertIn("/test/contracts/PR_001.md", prompt)
        self.assertIn("/test/docs/PRD.md", prompt)
        self.assertIn("/test/playbooks/coder_playbook.md", prompt)
        self.assertNotIn("--- PR Contract", prompt)
        self.assertNotIn("--- PRD", prompt)
        self.assertNotIn("--- CODER PLAYBOOK ---", prompt)

    def test_initial_v2_prompt_inlines_coder_playbook_and_keeps_pr_contract_and_prd_as_refs(self):
        playbook_path = os.path.join(self.temp_dir, "coder_playbook_v2.md")
        with open(playbook_path, "w", encoding="utf-8") as f:
            f.write("# Coder Playbook V2\n\nUse Red → Green → Refactor.\n")

        envelope = build_startup_envelope(
            role="coder",
            workdir="/test/workdir",
            out_dir="/test/run_dir",
            references={
                "pr_contract_file": "/test/contracts/PR_001.md",
                "prd_file": "/test/docs/PRD.md",
                "playbook_path": playbook_path,
            },
            contract_params={},
            mode="initial_v2",
        )

        prompt = render_envelope_to_prompt(envelope)

        self.assertIn("## CODER PLAYBOOK", prompt)
        self.assertIn("# Coder Playbook V2", prompt)
        self.assertIn("Use Red → Green → Refactor.", prompt)
        self.assertIn("/test/contracts/PR_001.md", prompt)
        self.assertIn("/test/docs/PRD.md", prompt)
        self.assertNotIn("coder_playbook_v2.md", prompt)
        self.assertNotIn("read playbook", prompt.lower())
        self.assertNotIn("--- PR Contract", prompt)
        self.assertNotIn("--- PRD", prompt)

    def test_build_verifier_startup_envelope_splits_multi_prd_references(self):
        envelope = build_startup_envelope(
            role="verifier",
            workdir="/tmp/workdir",
            out_dir="/tmp/run_dir",
            references={
                "prd_files": "/tmp/PRD_A.md, /tmp/PRD_B.md",
                "playbook_path": "/tmp/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/tmp/uat_report.json",
                "output_schema": {"status": "string"},
            },
        )

        self.assertEqual(envelope["role"], "verifier")
        refs_by_id = {ref["id"]: ref for ref in envelope["reference_index"]}
        self.assertEqual(refs_by_id["prd_1"]["path"], "/tmp/PRD_A.md")
        self.assertEqual(refs_by_id["prd_2"]["path"], "/tmp/PRD_B.md")
        self.assertEqual(refs_by_id["verifier_playbook"]["path"], "/tmp/verifier_playbook.md")
        self.assertTrue(all(ref["required"] for ref in refs_by_id.values()))
        self.assertTrue(all(ref["priority"] == 1 for ref in refs_by_id.values()))

    def test_rendered_verifier_prompt_is_contract_first_and_path_driven(self):
        envelope = build_startup_envelope(
            role="verifier",
            workdir="/tmp/workdir",
            out_dir="/tmp/run_dir",
            references={
                "prd_files": "/tmp/PRD_A.md, /tmp/PRD_B.md",
                "playbook_path": "/tmp/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/tmp/uat_report.json",
                "output_schema": {"status": "string"},
            },
        )

        prompt = render_envelope_to_prompt(envelope)

        self.assertIn("## EXECUTION CONTRACT", prompt)
        self.assertIn("/tmp/PRD_A.md", prompt)
        self.assertIn("/tmp/PRD_B.md", prompt)
        self.assertIn("/tmp/verifier_playbook.md", prompt)
        self.assertIn("/tmp/uat_report.json", prompt)
        self.assertNotIn("ATTENTION: Your root workspace is rigidly locked", prompt)
        self.assertNotIn("You are the UAT Verifier Agent", prompt)

    def test_verifier_envelope_includes_read_only_and_output_schema_contract(self):
        output_schema = {
            "status": "PASS|FAIL",
            "executive_summary": "string",
            "verification_details": [
                {
                    "requirement": "string",
                    "status": "PASS|FAIL",
                    "evidence": "string",
                    "comments": "string",
                }
            ],
        }
        envelope = build_startup_envelope(
            role="verifier",
            workdir="/tmp/workdir",
            out_dir="/tmp/run_dir",
            references={
                "prd_files": "/tmp/PRD_A.md",
                "playbook_path": "/tmp/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/tmp/uat_report.json",
                "output_schema": output_schema,
            },
        )

        execution_contract = "\n".join(envelope["execution_contract"])
        self.assertIn("Read-Only", execution_contract)
        self.assertIn("/tmp/uat_report.json", execution_contract)
        self.assertIn("status", execution_contract)
        self.assertIn("executive_summary", execution_contract)
        self.assertIn("verification_details", execution_contract)

    def test_verifier_envelope_includes_evidence_only_boundary_rules(self):
        envelope = build_startup_envelope(
            role="verifier",
            workdir="/tmp/workdir",
            out_dir="/tmp/run_dir",
            references={
                "prd_files": "/tmp/PRD_A.md",
                "playbook_path": "/tmp/verifier_playbook.md",
            },
            contract_params={
                "output_file": "/tmp/uat_report.json",
                "output_schema": {"status": "string"},
            },
        )

        execution_contract = envelope["execution_contract"]
        for rule in self.VERIFIER_EVIDENCE_ONLY_BOUNDARY_RULES:
            self.assertIn(rule, execution_contract)

        prompt = render_envelope_to_prompt(envelope)
        for rule in self.VERIFIER_EVIDENCE_ONLY_BOUNDARY_RULES:
            self.assertIn(rule, prompt)

    def test_render_envelope_to_prompt(self):
        envelope = {
            "execution_contract": ["A clause"],
            "reference_index": [{"id": "1", "kind": "test"}],
            "final_checklist": ["Check 1"],
        }
        prompt = render_envelope_to_prompt(envelope)
        self.assertIn("EXECUTION CONTRACT", prompt)
        self.assertIn("REFERENCE INDEX", prompt)
        self.assertIn("FINAL CHECKLIST", prompt)

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
        self.assertIn("EXECUTION CONTRACT", prompt)

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

    def test_auditor_prologue_exact_match(self):
        expected = (
            "你是本系统的首席架构师 (Principal Architect)，拥有极高的代码审美和架构洁癖。"
            "你的唯一使命是：\"绝不让一个定义不清、会引入技术债、违背最佳设计模式的 PRD，"
            "污染我们的代码库。\""
        )
        self.assertEqual(ROLE_PROLOGUES.get("auditor"), expected)

if __name__ == '__main__':
    unittest.main()
