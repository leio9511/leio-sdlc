import os
import json
import tempfile
import subprocess
import time
import sys
import uuid
import shutil
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AgentResult:
    session_key: str
    stdout: str
    stderr: str = ""
    return_code: int = 0

# Dynamic module resolution for monorepo development vs production deployment
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
try:
    from notification_formatter import format_notification
except ImportError:
    # If format_notification isn't easily available, fallback
    def format_notification(event_type, context):
        return f"[{event_type}] {context}"

def notify_channel(effective_channel, msg, event_type=None, context=None):
    if event_type:
        msg = format_notification(event_type, context or {})
    else:
        msg = f"🤖 [SDLC Engine] {msg}"
    if effective_channel:
        if not shutil.which("openclaw"):
            channel = effective_channel
            logger.info(f"[Channel Message to {channel}]: {msg}")
            return
            
        cmd = ["openclaw", "message", "send"]
        if ":" in effective_channel:
            parts = effective_channel.split(":")
            if len(parts) >= 2:
                cmd.extend(["--channel", parts[0]])
                cmd.extend(["-t", ":".join(parts[1:])])
        else:
            cmd.extend(["-t", effective_channel])
        cmd.extend(["-m", msg])
        
        # When running in test mode, do not actually call openclaw message send
        test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"
        if not test_mode:
            subprocess.run(cmd, capture_output=True)

def resolve_cmd(cmd_name):
    # Dynamic path resolution with $AGENT_SKILLS_DIR fallback
    cmd_path = shutil.which(cmd_name)
    if cmd_path:
        return cmd_path
        
    skills_dir = os.environ.get("AGENT_SKILLS_DIR", os.path.expanduser("~/.openclaw/skills"))
    fallback_path = os.path.join(skills_dir, cmd_name, "scripts", f"{cmd_name}.sh")
    if os.path.exists(fallback_path):
        return fallback_path
        
    fallback_path = os.path.join(skills_dir, cmd_name, cmd_name)
    if os.path.exists(fallback_path):
        return fallback_path
        
    return cmd_name

def invoke_agent(task_string, session_key=None, role=None, run_dir=None):
    """
    Core router that dynamically selects the CLI driver and flags based on the active LLM_DRIVER.
    Supports dynamic path resolution and isolated E2E testing integration.
    """
    if not session_key:
        session_key = f"subtask-{uuid.uuid4().hex[:8]}"

    # Safety Guardrails: JIT (Just-In-Time) Prompt guardrails enforcing the File System API.
    jit_guardrail = (
        "\n\n## MANDATORY FILE I/O POLICY\n"
        "All agents MUST use the native `read`, `write`, and `edit` tool APIs for all file operations whenever possible. "
        "NEVER use shell commands (e.g., `exec` with `echo`, `cat`, `sed`, `awk`) to read, create, or modify file contents. "
        "This is a strict, non-negotiable requirement to prevent escaping errors, syntax corruption, and context pollution.\n"
    )
    task_string += jit_guardrail

    if run_dir and os.path.exists(run_dir):
        temp_dir = os.path.join(run_dir, ".tmp")
    else:
        temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)

    fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"sdlc_prompt_{session_key}_", dir=temp_dir, text=True)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(task_string)
        
        secure_msg = f"Read your complete task instructions from {path}. Do not modify this file."

        if "SDLC_MOCK_LLM_RESPONSE" in os.environ:
            if os.environ.get("SDLC_MOCK_INSPECT_FILE_PERMS") == "1":
                perms = oct(os.stat(path).st_mode)[-3:]
                print(f"FILE:{path}:PERMS:{perms}")
            return AgentResult(session_key=session_key, stdout=os.environ["SDLC_MOCK_LLM_RESPONSE"], return_code=0)
        
    # Determine LLM driver
        llm_driver = os.environ.get("LLM_DRIVER", "openclaw").lower()
        
        # Check session map
        session_map_file = os.path.join(temp_dir, f".session_map_{session_key}.json")
        actual_id = None
        if os.path.exists(session_map_file):
            try:
                with open(session_map_file, "r") as f:
                    mapping = json.load(f)
                    actual_id = mapping.get("actual_id")
            except Exception:
                pass

        if llm_driver == "gemini":
            from config import DEFAULT_GEMINI_MODEL
            # --yolo is CRITICAL: prevents interactive Y/n prompt blocking in headless/CI environments
            model = os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL") or DEFAULT_GEMINI_MODEL
            cmd_exec = resolve_cmd("gemini")
            if actual_id:
                cmd = [cmd_exec, "--yolo", "-p", secure_msg, "-r", actual_id]
            else:
                cmd = [cmd_exec, "--yolo", "-p", secure_msg, "--model", model]
        else:
            cmd_exec = resolve_cmd("openclaw")
            if actual_id:
                cmd = [cmd_exec, "agent", "--session-id", actual_id, "-m", secure_msg]
            else:
                cmd = [cmd_exec, "agent", "--session-id", session_key, "-m", secure_msg]
            
        print(f"[{role or 'system'}] Invoking agent driver: {' '.join(cmd)}")
        
        for attempt in range(3):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
                
                # Session Mapping anti-race capture
                if llm_driver == "gemini" and not actual_id:
                    list_cmd = [cmd_exec, "--list-sessions", "-o", "json"]
                    list_res = subprocess.run(list_cmd, capture_output=True, text=True)
                    if list_res.returncode == 0:
                        try:
                            sessions = json.loads(list_res.stdout)
                            for s in sessions:
                                if "prompt" in s and path in s["prompt"]:
                                    with open(session_map_file, "w") as f:
                                        json.dump({"actual_id": s["id"]}, f)
                                    break
                        except Exception as e:
                            print(f"Error parsing session list: {e}", file=sys.stderr)
                elif llm_driver == "openclaw" and not actual_id:
                    with open(session_map_file, "w") as f:
                        json.dump({"actual_id": session_key}, f)

                return AgentResult(session_key=session_key, stdout=result.stdout, stderr=result.stderr, return_code=result.returncode)
            else:
                if attempt < 2:
                    time.sleep(3 * (2 ** attempt))
                else:
                    print(f"Error: subprocess returned non-zero exit status {result.returncode}", file=sys.stderr)
                    if result.stderr:
                        print(f"Stderr: {result.stderr}", file=sys.stderr)
                    sys.exit(1)
    finally:
        if os.path.exists(path):
            os.remove(path)
            
    return None

RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))

def build_prompt(role, **kwargs):
    # Support dual-source prompt loading
    import inspect
    caller_frame = inspect.currentframe().f_back
    caller_file = caller_frame.f_globals.get('__file__') if caller_frame else sys.argv[0]
    caller_dir = os.path.dirname(os.path.abspath(caller_file))
    local_config_path = os.path.join(os.path.dirname(caller_dir), "config", "prompts.json")
    
    base_dir = os.path.dirname(RUNTIME_DIR)
    global_config_path = os.path.join(base_dir, "config", "prompts.json")
    
    print(f""); template = ""
    if os.path.exists(local_config_path):
        with open(local_config_path, "r") as f:
            try:
                prompts = json.load(f)
                template = prompts.get(role, "")
            except Exception:
                pass
                
    if not template and os.path.exists(global_config_path) and global_config_path != local_config_path:
        with open(global_config_path, "r") as f:
            try:
                prompts = json.load(f)
                template = prompts.get(role, "")
            except Exception:
                pass
                
    for k, v in kwargs.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template