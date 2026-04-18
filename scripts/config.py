import os

# System-wide configuration constants
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_LLM_ENGINE = "gemini"

SDLC_SKILLS_ROOT = os.getenv("SDLC_SKILLS_ROOT", os.path.expanduser("~/.openclaw/skills"))
