status: blocked_fatal

## Goal
Implement `scripts/build_release.sh` to construct the sterile `dist/` directory using an explicit allowlist copy. Implement `scripts/test_build_release.sh` to verify isolation bounds. Hook the test into `preflight.sh`.

## Acceptance Criteria
- `scripts/build_release.sh` creates a `dist/` folder with only allowed files.
- `scripts/test_build_release.sh` confirms docs/tests/sdlc/git are excluded.
- `./preflight.sh` passes with the new test.


> [Escalation] Tier 1 Reset triggered due to Coder failure or Arbitrator rejection.
