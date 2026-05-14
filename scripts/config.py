import os
import json

# System-wide configuration constants
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro-preview"
DEFAULT_LLM_ENGINE = "gemini"
OPENCLAW_MODEL_MISMATCH_ERROR = "[FATAL] OpenClaw isolated agent model mismatch. Requested model '{requested_model}', but agent '{agent_id}' is bound to '{actual_model}'. Refusing to continue with non-deterministic execution."

ALLOWED_RUNTIME_ROOTS_CONFIG_KEY = "ALLOWED_RUNTIME_ROOTS"
DEFAULT_ALLOWED_RUNTIME_ROOTS = [
    "~/.openclaw/skills",
    "~/.gemini/skills",
]

SDLC_SKILLS_ROOT = os.getenv("SDLC_SKILLS_ROOT", os.path.expanduser("~/.openclaw/skills"))
SDLC_RUNTIME_DIR = os.getenv("SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))
NOTIFICATION_BRIDGE_BINARY = os.getenv("NOTIFICATION_BRIDGE_BINARY", "openclaw")
SDLC_NOTIFICATION_VERSION = int(os.getenv("SDLC_NOTIFICATION_VERSION", "2"))


def load_or_merge_config(sdlc_root):
    template_path = os.path.join(sdlc_root, "config", "sdlc_config.json.template")
    config_path = os.path.join(sdlc_root, "config", "sdlc_config.json")

    config_template = {}
    if os.path.exists(template_path):
        with open(template_path, "r") as f:
            config_template = json.load(f)

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                local_config = json.load(f)
            except json.JSONDecodeError:
                local_config = {}
        changed = False
        for k, v in config_template.items():
            if k not in local_config:
                local_config[k] = v
                changed = True
        if changed and os.environ.get("SDLC_TEST_MODE") != "true":
            # PR-002: Prevent physical config write if in test mode
            with open(config_path, "w") as fw:
                json.dump(local_config, fw, indent=4)
        return local_config
    else:
        if os.environ.get("SDLC_TEST_MODE") != "true":
            # PR-002: Prevent physical config write if in test mode
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(config_template, f, indent=4)
        return config_template


def get_allowed_runtime_roots(app_config):
    if ALLOWED_RUNTIME_ROOTS_CONFIG_KEY not in app_config:
        return None
    return app_config[ALLOWED_RUNTIME_ROOTS_CONFIG_KEY]

