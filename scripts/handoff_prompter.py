class HandoffPrompter:
    PROMPTS = {
        "happy_path": "[SUCCESS_HANDOFF]\\n[ACTION REQUIRED FOR MANAGER]\\nThe pipeline has finished. You must now: 1. Update PRD status. 2. Close the Issue strictly using the full path to the issue_tracker skill: python3 ~/.openclaw/skills/issue_tracker/scripts/issues.py. 3. Update STATE.md. 4. Wait and Report completion to the Boss.",
        "dirty_workspace": "[FATAL_STARTUP]\\n[ACTION REQUIRED FOR MANAGER]\\nWorkspace is dirty. There are uncommitted files. NEVER blindly delete or commit them! You MUST use 'git stash' to safely preserve the state, or abort and wait for human intervention.",
        "planner_failure": "[FATAL_PLANNER]\\n[ACTION REQUIRED FOR MANAGER]\\nPlanner failed. You must read planner logs and refine the PRD.",
        "git_checkout_error": "[FATAL_GIT] Git checkout failed. Workspace preserved. Invoke --cleanup to quarantine.",
        "fatal_crash": "[FATAL_CRASH] Orchestrator crashed. Process groups reaped. Workspace preserved. Read traceback. Invoke --cleanup to quarantine the branch.",
        "fatal_interrupt": "[FATAL_INTERRUPT] Aborted via SIGINT/SIGTERM. Process groups reaped. Workspace preserved.",
        "missing_channel": "[FATAL_STARTUP]\\n[ACTION REQUIRED FOR MANAGER] Missing channel parameter.",
        "dead_end": "[FATAL_ESCALATION]\\n[ACTION REQUIRED FOR MANAGER]\\nDead End reached. You must read \`Review_Report.md\` and alert the Boss explicitly.",
        "startup_validation_failed": "[FATAL_STARTUP]\\n[ACTION REQUIRED FOR MANAGER]\\nStartup validation failed. No system state was modified. Correct your CLI command/parameters and retry.",
        "invalid_git_boundary": "[FATAL_STARTUP]\\n[ACTION REQUIRED FOR MANAGER]\\nInvalid Git boundary. You must run this from the root of a Git repository on the master/main branch.",
        "pipeline_locked": "[FATAL_LOCK]\\n[ACTION REQUIRED FOR MANAGER]\\nAnother SDLC pipeline is actively running in this workspace. You must wait for it to finish. DO NOT modify the workspace."
    }

    @classmethod
    def get_prompt(cls, condition: str) -> str:
        return cls.PROMPTS.get(condition, "[ACTION REQUIRED FOR MANAGER]\\nUnknown exit condition.")
