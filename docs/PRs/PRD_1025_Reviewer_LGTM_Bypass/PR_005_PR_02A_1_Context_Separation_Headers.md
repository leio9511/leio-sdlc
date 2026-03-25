# PR Contract: PR_02A_1_Context_Separation_Headers

## Context
The prompt generated for the Reviewer needs clear section headers separating `recent_history.diff` from `current_review.diff`. This is the first step in fixing the Reviewer History Overreaction bug by structurally isolating the context.

## Tasks for Coder
1. Refactor `scripts/spawn_reviewer.py` to include clear, unambiguous section headers separating history from the current diff in the generated prompt.
2. Add unit tests validating that the output of `spawn_reviewer.py` contains these specific structural section headers.

## Constraints
- Must include both the failing tests for the headers and their passing implementation in this single PR.
- CI pipeline must pass (100% green tests).
