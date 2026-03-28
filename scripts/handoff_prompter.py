class HandoffPrompter:
    PROMPTS = {
        "happy_path": "[SUCCESS_HANDOFF]\n[ACTION REQUIRED FOR MANAGER]\nThe pipeline has finished. You must now: 1. Close the PRD. 2. Close the Issue. 3. Update STATE.md.",
        "dirty_workspace": "[FATAL_STARTUP]\n[ACTION REQUIRED FOR MANAGER]\nWorkspace is dirty. You must run `git commit` or `git stash` to clean the workspace before proceeding.",
        "planner_failure": "[FATAL_PLANNER]\n[ACTION REQUIRED FOR MANAGER]\nPlanner failed. You must read planner logs and refine the PRD.",
        "git_checkout_error": "[FATAL_GIT] Git checkout failed. Workspace preserved. Invoke --cleanup to quarantine.",
        "fatal_crash": "[FATAL_CRASH] Orchestrator crashed. Process groups reaped. Workspace preserved. Read traceback. Invoke --cleanup to quarantine the branch.",
        "fatal_interrupt": "[FATAL_INTERRUPT] Aborted via SIGINT/SIGTERM. Process groups reaped. Workspace preserved.",
        "missing_channel": "[FATAL_STARTUP]\n[ACTION REQUIRED FOR MANAGER] Missing channel parameter.",
        "dead_end": "[FATAL_ESCALATION]\n[ACTION REQUIRED FOR MANAGER]\nDead End reached. You must read `Review_Report.md` and alert the Boss explicitly.",
    }

    @classmethod
    def get_prompt(cls, condition: str) -> str:
        return cls.PROMPTS.get(condition, "[ACTION REQUIRED FOR MANAGER]\nUnknown exit condition.")
