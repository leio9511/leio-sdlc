# PR Contract: PR_02A_2_Explicit_Reviewer_Instructions

## Context
Building on the structural separation added in the previous PR, the Reviewer must now be explicitly instructed on how to handle the separated diff sections to prevent false-positive rejections.

## Tasks for Coder
1. Update `scripts/spawn_reviewer.py` to explicitly instruct the Reviewer that `recent_history.diff` is strictly read-only reference material.
2. Add instructions mandating that all security checks, redlines, and logic validations be strictly applied ONLY to `current_review.diff`.
3. Add unit tests validating that these explicit instructional constraints are correctly injected into the generated prompt.

## Constraints
- Must include both the failing tests for the new instructions and their passing implementation in this single PR.
- CI pipeline must pass (100% green tests).
