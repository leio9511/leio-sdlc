status: open

## Goal
Modify `deploy.sh` to execute `scripts/build_release.sh` and exit on failure. Update the sync source to `$DEV_DIR/dist/`.

## Acceptance Criteria
- `deploy.sh` runs build before deployment.
- Deployment sources only from `dist/`.
