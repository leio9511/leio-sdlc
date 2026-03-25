status: open

---
title: "Micro-PR 1: Core Blue/Green Deployment & Pruning"
status: open
dependencies: []
---
# Context
Implement Capistrano-style symlink deployment in `deploy.sh` and its corresponding testing script `test_blue_green_deploy.sh`.

# Requirements
1. Update `deploy.sh` to safely migrate legacy directories to symlinks (if `~/.openclaw/skills/<slug>` is a directory, remove it).
2. Generate release ID (`date +"%Y%m%d_%H%M%S"`) and copy artifacts to `~/.openclaw/.releases/<slug>/$RELEASE_ID/`.
3. Implement atomic swap by creating a temporary symlink and moving it over the main runtime symlink.
4. Auto-cleanup: keep only the latest 3 releases in the `.releases` directory.
5. Create `scripts/test_blue_green_deploy.sh` that mocks directories and implements Tests T1 (Initial Deployment & Migration), T2 (Atomic Version Progression), and T4 (Auto-Cleanup Limit).
