import config
from agent_driver import build_prompt

class HandoffPrompter:
    @classmethod
    def get_prompt(cls, condition: str) -> str:
        prompt = build_prompt(f"handoff_{condition}")
        if not prompt:
            return "[ACTION REQUIRED FOR MANAGER]\nUnknown exit condition."
        # Replace legacy format strings with dynamic runtime path
        prompt = prompt.replace("{SDLC_SKILLS_ROOT}", getattr(config, "SDLC_RUNTIME_DIR", config.SDLC_SKILLS_ROOT))
        prompt = prompt.replace("{SDLC_RUNTIME_DIR}", getattr(config, "SDLC_RUNTIME_DIR", config.SDLC_SKILLS_ROOT))
        return prompt
