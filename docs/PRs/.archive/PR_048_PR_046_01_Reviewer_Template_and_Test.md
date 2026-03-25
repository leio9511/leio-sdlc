status: open

---
status: open
---
# PR Contract: Reviewer Template and Guardrail Test

## Description
Create the physical Markdown template for the Reviewer agent and the corresponding TDD bash test for the missing artifact guardrail.

## Tasks
1. Create `TEMPLATES/Review_Report.md.template` with checkboxes for `[LGTM]` or `[ACTION_REQUIRED]`, plus sections for Feedback and Security checks.
2. Create `scripts/test_reviewer_artifact_guardrail.sh` to test the two scenarios (Agent fails to write file, Agent succeeds).
