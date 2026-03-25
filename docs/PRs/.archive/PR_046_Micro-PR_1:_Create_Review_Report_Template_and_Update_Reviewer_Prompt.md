status: open

---
status: open
---
# Micro-PR 1: Create Review Report Template and Update Reviewer Prompt

## Objective
Create the physical artifact template for the Reviewer and inject it into the spawning script's prompt.

## Tasks
1. Create `TEMPLATES/Review_Report.md.template` with structured sections for verdict (`[LGTM]` or `[ACTION_REQUIRED]`), "Feedback & Action Items", and "Security & Redline Checks".
2. Modify `scripts/spawn_reviewer.py` to read `TEMPLATES/Review_Report.md.template`.
3. Inject the template contents into the `task_string` passed to the `openclaw agent` call in `scripts/spawn_reviewer.py`.
4. Add the CRITICAL DIRECTIVE to the prompt: `"You MUST use the \`write\` tool to save your final evaluation into exactly '{workdir}/review_report.txt' using the provided template. DO NOT just print the evaluation in the chat."`

## Acceptance Criteria
- `TEMPLATES/Review_Report.md.template` exists and contains required sections.
- `scripts/spawn_reviewer.py` reads and injects the template.