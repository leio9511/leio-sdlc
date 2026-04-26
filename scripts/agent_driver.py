import os
import json
import tempfile
import subprocess
import time
import sys
import uuid
import shutil
import logging
import re
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
from notification_formatter import format_notification

def notify_channel(effective_channel, msg, event_type=None, context=None):
    if event_type:
        msg = format_notification(event_type, context or {})
    else:
        msg = f"🤖 [SDLC Engine] {msg}"
    
    if not effective_channel:
        return

    import config
    if getattr(config, "SDLC_NOTIFICATION_VERSION", 2) == 1:
        # Legacy Path
        if not shutil.which("openclaw"):
            logger.info(f"[Channel Message to {effective_channel}]: {msg}")
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
        
        test_mode = os.environ.get("SDLC_TEST_MODE", "").lower() == "true"
        if not test_mode:
            subprocess.run(cmd, capture_output=True)
    else:
        # New Strategy Layer: Delegate routing and delivery to NotificationRouter.
        # Ensure routing failures propagate as a fatal runtime error.
        from utils_notification import NotificationRouter
        try:
            NotificationRouter.send(effective_channel, msg)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[FATAL] Notification delivery failed: {e}", file=sys.stderr)
            sys.exit(1)

def send_ignition_handshake(channel: str) -> None:
    import config
    if getattr(config, "SDLC_NOTIFICATION_VERSION", 2) == 1:
        # Legacy Handshake (as it was in orchestrator.py/spawn_auditor.py)
        msg = format_notification("sdlc_handshake", {})
        notify_channel(channel, msg)
    else:
        from utils_notification import send_ignition_handshake as utils_handshake
        try:
            utils_handshake(channel)
        except SystemExit:
            raise
        except Exception as e:
            print(f"[FATAL] Handshake delivery failed: {e}", file=sys.stderr)
            sys.exit(1)

def resolve_cmd(cmd_name):
    # Dynamic path resolution with $AGENT_SKILLS_DIR fallback
    cmd_path = shutil.which(cmd_name)
    if cmd_path:
        return cmd_path
        
    import config
    runtime_dir = getattr(config, "SDLC_RUNTIME_DIR", os.path.expanduser("~/.openclaw/skills"))
    runtime_path = os.path.join(runtime_dir, cmd_name, "scripts", f"{cmd_name}.sh")
    if os.path.exists(runtime_path):
        return runtime_path
        
    runtime_path = os.path.join(runtime_dir, cmd_name, cmd_name)
    if os.path.exists(runtime_path):
        return runtime_path
        
    skills_dir = os.environ.get("AGENT_SKILLS_DIR", os.path.expanduser("~/.openclaw/skills"))
    fallback_path = os.path.join(skills_dir, cmd_name, "scripts", f"{cmd_name}.sh")
    if os.path.exists(fallback_path):
        return fallback_path
        
    fallback_path = os.path.join(skills_dir, cmd_name, cmd_name)
    if os.path.exists(fallback_path):
        return fallback_path
        
    return cmd_name

def normalize_openclaw_model_suffix(model: str) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '-', (model or '').strip().lower()).strip('-')
    return normalized or "unknown"

def get_openclaw_agent_id(model: str) -> str:
    return f"sdlc-generic-openclaw-{normalize_openclaw_model_suffix(model)}"

def openclaw_agent_exists(list_stdout: str, agent_id: str) -> bool:
    prefix = f"- {agent_id}"
    for line in (list_stdout or '').splitlines():
        stripped = line.strip()
        if stripped == prefix or stripped.startswith(f"{prefix} "):
            return True
    return False

def parse_openclaw_agent_model(agent_card_stdout: str) -> str | None:
    for raw_line in (agent_card_stdout or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith('model:'):
            return line.split(':', 1)[1].strip() or None
        if lowered.startswith('model '):
            return line.split(None, 1)[1].strip() or None
    return None

def validate_openclaw_agent_model(cmd_exec: str, agent_id: str, requested_model: str) -> None:
    from config import OPENCLAW_MODEL_MISMATCH_ERROR

    list_cmd = [cmd_exec, 'agents', 'list']
    list_res = subprocess.run(list_cmd, capture_output=True, text=True)
    
    lines = list_res.stdout.splitlines()
    agent_block = []
    found = False
    prefix = f"- {agent_id}"
    for line in lines:
        stripped = line.strip()
        if not found and (stripped == prefix or stripped.startswith(f"{prefix} ")):
            found = True
            agent_block.append(line)
            continue
        if found:
            # If we hit another agent block (starts with "- ") or any other 
            # non-indented line that isn't empty, we stop.
            # In practice, agents list output is indented after the "- id" line.
            if stripped.startswith("- "):
                break
            agent_block.append(line)
    
    if not found:
        return

    actual_model = parse_openclaw_agent_model("\n".join(agent_block))
    if actual_model and actual_model != requested_model:
        print(
            OPENCLAW_MODEL_MISMATCH_ERROR.format(
                requested_model=requested_model,
                agent_id=agent_id,
                actual_model=actual_model,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

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
            from config import DEFAULT_GEMINI_MODEL
            model = os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL") or DEFAULT_GEMINI_MODEL
            cmd_exec = resolve_cmd("openclaw")
            agent_id = get_openclaw_agent_id(model)
            
            list_cmd = [cmd_exec, "agents", "list"]
            list_res = subprocess.run(list_cmd, capture_output=True, text=True)
            agent_exists = openclaw_agent_exists(list_res.stdout, agent_id)
            if not agent_exists:
                home_dir = os.environ.get("HOME_MOCK") or os.environ.get("HOME", os.path.expanduser("~"))
                agent_ws = os.path.join(home_dir, ".openclaw", "agents", agent_id, "workspace")
                os.makedirs(agent_ws, exist_ok=True)
                create_cmd = [cmd_exec, "agents", "add", agent_id, "--non-interactive", "--model", model, "--workspace", agent_ws]
                subprocess.run(create_cmd, capture_output=True)
                
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                templates_dir = os.path.join(base_dir, "TEMPLATES", "openclaw_execution_agent")
                if os.path.exists(templates_dir):
                    import shutil
                    for item in os.listdir(templates_dir):
                        s = os.path.join(templates_dir, item)
                        d = os.path.join(agent_ws, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d, dirs_exist_ok=True)
                        else:
                            shutil.copy2(s, d)
            else:
                validate_openclaw_agent_model(cmd_exec, agent_id, model)

            if actual_id:
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", actual_id, "-m", secure_msg]
            else:
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", session_key, "-m", secure_msg]
            
        print(f"[{role or 'system'}] Invoking agent driver: {' '.join(cmd)}")
        
        for attempt in range(3):
            # Native inheritance: Ensure GEMINI_API_KEY is natively inherited for stateless execution
            run_env = os.environ.copy()
            if os.environ.get("GEMINI_API_KEY"):
                run_env["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY")
                
            result = subprocess.run(cmd, capture_output=True, text=True, env=run_env)
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