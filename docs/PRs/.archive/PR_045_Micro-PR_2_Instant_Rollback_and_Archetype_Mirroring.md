status: open

---
title: "Micro-PR 2: Instant Rollback & Archetype Mirroring"
status: open
dependencies: ["Micro-PR 1: Core Blue/Green Deployment & Pruning"]
---
# Context
Implement instant rollback capability and mirror the blue/green deployment architecture to the `AgentSkill_Archetype`.

# Requirements
1. Create `scripts/rollback.sh` that detects available releases, identifies the previous release, atomically swaps the symlink back to it, and restarts the Gateway.
2. Update `scripts/test_blue_green_deploy.sh` to include Test T3 (Instant Rollback) verifying sub-second rollback.
3. Mirror the updated `deploy.sh` and the new `scripts/rollback.sh` to `TEMPLATES/AgentSkill_Archetype/deploy.sh` and `TEMPLATES/AgentSkill_Archetype/scripts/rollback.sh`.
