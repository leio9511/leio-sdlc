status: open

---
status: open
---
# PR Contract: Implement Reviewer Artifact Guardrail

## Description
Update the `spawn_reviewer.py` script to inject the template into the agent's prompt and enforce the physical existence of `review_report.txt`.

## Tasks
1. Update `scripts/spawn_reviewer.py` to read `TEMPLATES/Review_Report.md.template`.
2. Inject the template and the CRITICAL DIRECTIVE into the agent prompt.
3. Add a post-execution check for `{workdir}/review_report.txt`. If missing, print the fatal error to stderr and exit 1.
4. Ensure `./preflight.sh` passes with the new tests.
