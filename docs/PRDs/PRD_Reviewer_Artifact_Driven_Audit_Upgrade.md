---
Affected_Projects: [leio-sdlc]
Context_Workdir: /root/projects/leio-sdlc
---

# PRD: Reviewer Artifact-Driven Audit Upgrade (V2.6 - De-coupled Infrastructure)

## 1. Context & Problem (业务背景与核心痛点)
The current Reviewer integration relies on parsing JSON from chat stdout, which is fragile. Previous PRD attempts identified "Tool Deprivation" and "State Masking" as blockers. Furthermore, current prompts contain legacy references to `git` and `OpenClaw`, which creates unnecessary infrastructure coupling and dilutes the Reviewer's focus.

**Key Design Decisions from Boss:**
1. **Infrastructure De-coupling**: Remove all references to `git` (e.g., `git add`) and `OpenClaw` from the Reviewer's prompt. The Reviewer should be a pure logic auditor, independent of the underlying version control or orchestration platform.
2. **Artifact-Driven Handoff**: Use physical file delivery to eliminate parsing noise.
3. **Reference over Injection**: Pass file paths to keep prompts lean.

## 2. Requirements & User Stories (需求定义)
- **REQ-1 (Artifact-Centric Handoff)**: Reviewer must deliver the verdict via `review_report.json` using the `write` tool.
- **REQ-2 (Clean-Room Prompting)**: Purge all `git` and `OpenClaw` specific instructions from the Reviewer prompt.
- **REQ-3 (State-Aware Scaffolding)**: The script must instantiate the JSON template with `NOT_STARTED` before spawning.
- **REQ-4 (Rigid Verification)**: If the content remains `NOT_STARTED` post-execution, trigger a fatal audit failure.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### 3.1 `scripts/spawn_reviewer.py` Overhaul
1. **Scaffolding**: Before spawning, write the placeholder (Section 7.1) to `review_report.json`.
2. **Verification**: Post-execution, verify the status changed from `NOT_STARTED`.

### 3.2 Prompt & Playbook Realignment
1. **`config/prompts.json`**: Replace the `reviewer` field with the "De-coupled Caller" template in Section 7.2.
2. **`playbooks/reviewer_playbook.md`**: Overwrite with the infrastructure-agnostic source in Section 7.4.

### 3.3 Rollback Strategy
`python3 scripts/orchestrator.py --workdir /root/projects/leio-sdlc --prd-file PRD_Reviewer_Artifact_Driven_Audit_Upgrade.md --withdraw`

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario: Infrastructure-Agnostic Audit**
  - **Given** an audit request.
  - **When** the Reviewer agent analyzes the files.
  - **Then** the prompt must NOT contain the strings "git" or "OpenClaw".
  - **And** the audit must result in a valid `review_report.json` file.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **String Audit**: Verify that the generated Reviewer prompt is free of legacy infrastructure keywords.
- **Regression**: 100% pass on all 37 existing tests.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_reviewer.py`
- `config/prompts.json`
- `playbooks/reviewer_playbook.md`
- `TEMPLATES/Review_Report.json.template`

---

## 7. Hardcoded Content (硬编码内容)
> **[CRITICAL - STRING DETERMINISM]**

**7.1 `TEMPLATES/Review_Report.json.template` Content:**
```json
{
  "overall_assessment": "NOT_STARTED",
  "executive_summary": "Waiting for agent processing...",
  "findings": []
}
```

**7.2 Word-for-Word `reviewer` template for `config/prompts.json`:**
```markdown
ATTENTION: Your root workspace is rigidly locked to {workdir}. You are strictly forbidden from reading, writing, or modifying files outside this absolute path. 

⚠️ CRITICAL TOOLING QUIRK ⚠️
The native file tools (`read`, `write`, `edit`) suffer from CWD drift. They execute from the global root, NOT your project root. YOU MUST read the `{workdir}` variable passed in this prompt, and manually prepend it to EVERY relative file path you operate on. (e.g., `{workdir}/src/main.py`).

# SOURCE CODE / PROTOCOL
{playbook_content}

# FILE REFERENCES
@PRD_PATH: {prd_file}
@CONTRACT_PATH: {pr_file}
@DIFF_PATH: {diff_file}
@OUT_FILE_PATH: {out_file}

# EXECUTION CALL
NOW, execute: `perform_code_review(prd=@PRD_PATH, contract=@CONTRACT_PATH, diff=@DIFF_PATH, output=@OUT_FILE_PATH)`
```

**7.3 Word-for-Word `reviewer_system_alert` for `config/prompts.json`:**
```markdown
SYSTEM ALERT: The deliverable file '{out_file}' was not found or contained invalid JSON. Your task is to re-analyze the diff and correctly populate the file using the 'write' tool. No prose.
```

**7.4 Final High-Intensity `playbooks/reviewer_playbook.md` Source:**
```markdown
**SYSTEM:** You are a Code Audit Logic. Your mission is to generate a high-fidelity code review report in JSON format.
**DELIVERABLE:** You MUST use the `write` tool to save your final verdict into the file path provided in `output`.

**CAPABILITY:** `perform_code_review(prd, contract, diff, output)`

- **Step 1 (Analysis):** Use the `read` tool to analyze the files at `prd`, `contract`, and `diff`. Compare implementation against requirements.
- **Step 2 (Evidence):** For EVERY item in the PR Contract's "Implementation Scope" and "TDD Blueprint", you MUST find explicit evidence in the diff.
- **Step 3 (Delivery):** Use the `write` tool to save your final JSON verdict into the file path provided in `output`.
- **Step 4 (Format):** The file content must be a raw JSON object matching the schema below. DO NOT include markdown wrappers or conversational text inside the file.
- **Step 5 (Chat):** Your chat response must be brief (e.g., "Report written.").

- **Output JSON Schema:**
  {
  "overall_assessment": "(EXCELLENT|GOOD_WITH_MINOR_SUGGESTIONS|NEEDS_ATTENTION|NEEDS_IMMEDIATE_REWORK)",
  "executive_summary": "string",
  "findings": [
  {
  "file_path": "string",
  "line_number": "integer",
  "category": "(Correctness|PlanAlignmentViolation|ArchAlignmentViolation|Efficiency|Readability|Maintainability|DesignPattern|Security|Standard|PotentialBug|Documentation)",
  "severity": "(CRITICAL|MAJOR|MINOR|SUGGESTION|INFO)",
  "description": "Evidence-based description mapping requirement to diff.",
  "recommendation": "Actionable suggestion for improvement."
  }
  ]
  }
```

---

## Appendix: Architecture Evolution Trace (架构演进与审查追踪)
- **v2.6**: Infrastructure Decoupling. Purged all references to `git` and `OpenClaw` from Reviewer prompts to ensure platform independence and cognitive focus.
