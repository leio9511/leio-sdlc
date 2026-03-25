status: open

---
status: open
---
# Micro-PR 2: Implement Reviewer Artifact Guardrail and TDD Tests

## Objective
Implement a fail-fast Python guardrail to ensure the physical `review_report.txt` is created, and add TDD tests verifying this behavior.

## Tasks
1. Update `scripts/spawn_reviewer.py` to check for the existence of `{workdir}/review_report.txt` immediately after the `openclaw agent` subprocess completes.
2. If the file is missing, print `[FATAL] The Reviewer agent failed to generate the physical 'review_report.txt'. This is a severe process violation.` to `stderr` and `exit 1`.
3. Create `scripts/test_reviewer_artifact_guardrail.sh` to test two scenarios using a mock Reviewer:
   - Scenario 1: Mock Reviewer exits 0 but does not create `review_report.txt`. Assert `spawn_reviewer.py` exits 1 and prints the FATAL message.
   - Scenario 2: Mock Reviewer touches `review_report.txt` and exits 0. Assert `spawn_reviewer.py` exits 0.
4. Ensure `./preflight.sh` runs the new tests.

## Acceptance Criteria
- `spawn_reviewer.py` reliably crashes (`exit 1`) if the file is missing after execution.
- `scripts/test_reviewer_artifact_guardrail.sh` passes both scenarios.
- `./preflight.sh` passes with the new test included.