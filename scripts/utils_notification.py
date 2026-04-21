import os
import sys
import shutil
import subprocess
from abc import ABC, abstractmethod

# Dynamic path resolution to load config
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
import config

# Notification Templates from PRD
SDLC_HANDSHAKE = "🤝 [SDLC Engine] Initial Handshake successful. Channel linked."
BINARY_MISSING_ERROR = "[FATAL] Requested remote channel '{channel}' but the required message-delivery tool '{binary}' was not found in PATH."
NOTIFICATION_STDOUT_PREFIX = "[NOTIFY]"

class NotificationProvider(ABC):
    @abstractmethod
    def send(self, channel: str, message: str) -> None:
        pass

class StdoutProvider(NotificationProvider):
    def send(self, channel: str, message: str) -> None:
        print(f"{NOTIFICATION_STDOUT_PREFIX} {message}")
        sys.stdout.flush()

class OpenClawBridgeProvider(NotificationProvider):
    def send(self, channel: str, message: str) -> None:
        binary = config.NOTIFICATION_BRIDGE_BINARY
        binary_path = shutil.which(binary)
        
        test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"
        
        if not binary_path and not test_mode:
            # Absolute Fail-Fast
            print(BINARY_MISSING_ERROR.format(channel=channel, binary=binary), file=sys.stderr)
            sys.exit(1)
            
        cmd = [binary_path or binary, "message", "send"]
        if ":" in channel:
            parts = channel.split(":")
            if len(parts) >= 2:
                cmd.extend(["--channel", parts[0]])
                cmd.extend(["-t", ":".join(parts[1:])])
        else:
            cmd.extend(["-t", channel])
            
        cmd.extend(["-m", message])
        
        # When running in test mode, do not actually call openclaw message send
        if test_mode:
            print(f"DEBUG [Ignition Handshake]: {' '.join(cmd)}")
            if "invalid" in channel:
                from handoff_prompter import HandoffPrompter
                print(f"[FATAL] Invalid notification channel format. Failed to send handshake to '{channel}'. Expected format e.g., slack:CXXXXXX", file=sys.stderr)
                try:
                    print(HandoffPrompter.get_prompt("missing_channel"))
                except Exception:
                    pass
                sys.exit(1)
            return

        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[FATAL] Notification delivery failed to {channel}. Code: {res.returncode}", file=sys.stderr)
                if res.stderr:
                    print(res.stderr.strip(), file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"[FATAL] Notification delivery exception: {e}", file=sys.stderr)
            sys.exit(1)

class NotificationRouter:
    @staticmethod
    def send(channel: str, message: str) -> None:
        if not channel or channel == "stdout":
            provider = StdoutProvider()
        else:
            provider = OpenClawBridgeProvider()
        provider.send(channel, message)

def send_ignition_handshake(channel: str) -> None:
    NotificationRouter.send(channel, SDLC_HANDSHAKE)
