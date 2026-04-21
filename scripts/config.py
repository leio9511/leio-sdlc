import os

# System-wide configuration constants
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_LLM_ENGINE = "gemini"

SDLC_SKILLS_ROOT = os.getenv("SDLC_SKILLS_ROOT", os.path.expanduser("~/.openclaw/skills"))
SDLC_RUNTIME_DIR = os.getenv("SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))
NOTIFICATION_BRIDGE_BINARY = os.getenv("NOTIFICATION_BRIDGE_BINARY", "openclaw")
SDLC_NOTIFICATION_VERSION = int(os.getenv("SDLC_NOTIFICATION_VERSION", "2"))
