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


# ---------------------------------------------------------------------------
# Engine registry integration helpers
# ---------------------------------------------------------------------------

def _resolve_sdlc_root():
    """Resolve the SDLC project root for engine registry loading."""
    return os.environ.get("SDLC_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_engine_spec(sdlc_root, llm_driver):
    """Resolve LLM_DRIVER env var to an engine spec from the registry.

    Uses cli_alias first, then falls back to engine_id exact match.
    Fails closed if no matching engine is found.
    """
    from engine_registry import load_engine_registry
    registry = load_engine_registry(sdlc_root)
    for entry in registry["engines"].values():
        if entry.get("cli_alias") == llm_driver:
            return entry
    for entry in registry["engines"].values():
        if entry.get("engine_id") == llm_driver:
            return entry
    print(f"[FATAL] No engine registered for LLM_DRIVER '{llm_driver}'", file=sys.stderr)
    sys.exit(1)


def _resolve_direct_cli_model(engine_spec):
    """Resolve model for direct CLI engines.

    Priority: SDLC_MODEL > TEST_MODEL > execution.default_model > config.DEFAULT_GEMINI_MODEL
    """
    model = os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL")
    if not model:
        execution = engine_spec.get("execution", {})
        model = execution.get("default_model")
    if not model:
        from config import DEFAULT_GEMINI_MODEL
        model = DEFAULT_GEMINI_MODEL
    return model


def _assemble_direct_cli_command(engine_spec, secure_msg, workdir, model):
    """Assemble a CLI command from a direct_cli engine spec's execution subsection.

    Returns (cmd, env_extra_dict, timeout_seconds) tuple.
    """
    execution = engine_spec.get("execution", {})

    executable = execution.get("executable")
    if not executable:
        print("[FATAL] direct_cli engine spec missing required 'execution.executable'", file=sys.stderr)
        sys.exit(1)

    cmd_exec = resolve_cmd(executable)
    cmd = [cmd_exec]

    # workspace_arg
    workspace_arg = execution.get("workspace_arg")
    if workspace_arg is not None:
        if isinstance(workspace_arg, dict):
            raw_value = workspace_arg.get("value")
            if raw_value is None:
                # Dict-form workspace_arg with null value is invalid: skip to avoid
                # producing literal "None" in CLI args (e.g. "--add-dir None").
                pass
            else:
                flag = workspace_arg["flag"]
                value = str(raw_value).replace("{workdir}", workdir or "")
                cmd.extend([flag, value])
        elif isinstance(workspace_arg, list):
            for arg in workspace_arg:
                cmd.append(str(arg).replace("{workdir}", workdir or ""))
        else:
            cmd.append(str(workspace_arg).replace("{workdir}", workdir or ""))

    # permission_args
    permission_args = execution.get("permission_args", [])
    if permission_args:
        cmd.extend(permission_args)

    # sandbox_args
    sandbox_args = execution.get("sandbox_args", [])
    if sandbox_args:
        cmd.extend(sandbox_args)

    # one_shot_args + prompt
    one_shot_args = list(execution.get("one_shot_args", []))
    prompt_inserted = False
    for i, arg in enumerate(one_shot_args):
        if "{prompt}" in str(arg):
            one_shot_args[i] = str(arg).replace("{prompt}", secure_msg)
            prompt_inserted = True
            break
    cmd.extend(one_shot_args)
    if not prompt_inserted:
        cmd.append(secure_msg)

    # model_arg
    model_arg = execution.get("model_arg")
    if model_arg is not None and model:
        if isinstance(model_arg, dict):
            flag = model_arg["flag"]
            value = str(model_arg.get("value", "")).replace("{model}", model)
            cmd.extend([flag, value])
        elif isinstance(model_arg, list):
            for arg in model_arg:
                cmd.append(str(arg).replace("{model}", model))
        else:
            cmd.append(str(model_arg).replace("{model}", model))

    # env_extra — validate string-only keys/values, fatal on non-string
    env_extra = execution.get("env_extra", {})
    for k, v in env_extra.items():
        if not isinstance(k, str) or not isinstance(v, str):
            print(
                f"[FATAL] direct_cli env_extra key '{k}' (type {type(k).__name__}) "
                f"or value '{v}' (type {type(v).__name__}) is not a string",
                file=sys.stderr,
            )
            sys.exit(1)

    timeout_seconds = execution.get("timeout_seconds")

    return cmd, env_extra, timeout_seconds


# ---------------------------------------------------------------------------
# Core agent invocation
# ---------------------------------------------------------------------------

def invoke_agent(task_string, session_key=None, role=None, run_dir=None, thinking: str | None = None):
    """
    Core router that dynamically selects the CLI driver and flags based on the active LLM_DRIVER.
    Uses the engine registry to route between openclaw_native (stateful) and direct_cli (stateless).
    Supports dynamic path resolution and isolated E2E testing integration.
    """
    from thinking_resolver import resolve_thinking
    resolved_thinking = resolve_thinking(thinking)
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
        workdir = run_dir
    else:
        temp_dir = tempfile.gettempdir()
        workdir = temp_dir
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

        # --- Engine registry routing ---
        # Two-path architecture:
        #   stateful: openclaw_native → existing sessions_spawn path with session_map_file
        #   stateless: direct_cli → generic config-driven renderer (no session state)
        # Engine selection: LLM_DRIVER env var → engine spec via cli_alias or engine_id.
        llm_driver_raw = os.environ.get("LLM_DRIVER", "openclaw").lower()
        sdlc_root = _resolve_sdlc_root()
        engine_spec = _resolve_engine_spec(sdlc_root, llm_driver_raw)
        runtime_mode = engine_spec["runtime_mode"]

        session_map_file = os.path.join(temp_dir, f".session_map_{session_key}.json")

        if runtime_mode == "direct_cli":
            # Stateless: no session map read/write, no session discovery
            model = _resolve_direct_cli_model(engine_spec)
            cmd, env_extra, timeout_seconds = _assemble_direct_cli_command(
                engine_spec, secure_msg, workdir, model
            )
            actual_id = None

        elif runtime_mode == "openclaw_native":
            # Stateful: existing OpenClaw-native path (unchanged)
            from config import DEFAULT_GEMINI_MODEL
            model = os.environ.get("SDLC_MODEL") or os.environ.get("TEST_MODEL") or DEFAULT_GEMINI_MODEL
            cmd_exec = resolve_cmd("openclaw")
            agent_id = get_openclaw_agent_id(model)

            # Check session map for resume
            actual_id = None
            if os.path.exists(session_map_file):
                try:
                    with open(session_map_file, "r") as f:
                        mapping = json.load(f)
                        actual_id = mapping.get("actual_id")
                except Exception:
                    pass

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
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", actual_id, "--thinking", resolved_thinking, "-m", secure_msg]
            else:
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", session_key, "--thinking", resolved_thinking, "-m", secure_msg]

            env_extra = {}
            timeout_seconds = None

        else:
            print(f"[FATAL] Unsupported runtime_mode '{runtime_mode}' for engine '{engine_spec.get('engine_id')}'", file=sys.stderr)
            sys.exit(1)

        print(f"[{role or 'system'}] Invoking agent driver: {' '.join(cmd)}")

        for attempt in range(3):
            # Build run environment: inherit everything, then merge env_extra
            run_env = os.environ.copy()
            if os.environ.get("GEMINI_API_KEY"):
                run_env["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY")
            for k, v in env_extra.items():
                run_env[k] = v

            stdout_fd = None
            stderr_fd = None
            stdout_path = None
            stderr_path = None
            stdout = ""
            stderr = ""

            try:
                stdout_fd, stdout_path = tempfile.mkstemp(prefix=f"sdlc_stdout_{session_key}_", dir=temp_dir, text=True)
                stderr_fd, stderr_path = tempfile.mkstemp(prefix=f"sdlc_stderr_{session_key}_", dir=temp_dir, text=True)

                os.close(stdout_fd)
                stdout_fd = None
                os.close(stderr_fd)
                stderr_fd = None

                with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
                    process = subprocess.Popen(
                        cmd,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        start_new_session=True,
                        env=run_env,
                    )
                    try:
                        if timeout_seconds and timeout_seconds > 0:
                            return_code = process.wait(timeout=timeout_seconds)
                        else:
                            return_code = process.wait()
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                        return_code = -1

                with open(stdout_path, "r") as stdout_file:
                    stdout = stdout_file.read()
                with open(stderr_path, "r") as stderr_file:
                    stderr = stderr_file.read()
            finally:
                if stdout_fd is not None:
                    os.close(stdout_fd)
                if stderr_fd is not None:
                    os.close(stderr_fd)
                for capture_path in (stdout_path, stderr_path):
                    if capture_path:
                        try:
                            os.remove(capture_path)
                        except FileNotFoundError:
                            pass
                        except OSError:
                            pass

            if return_code == 0:
                print(stdout)

                # Session mapping: only for stateful (openclaw_native) engines
                if runtime_mode == "openclaw_native" and not actual_id:
                    with open(session_map_file, "w") as f:
                        json.dump({"actual_id": session_key}, f)

                return AgentResult(session_key=session_key, stdout=stdout, stderr=stderr, return_code=return_code)
            else:
                if attempt < 2:
                    time.sleep(3 * (2 ** attempt))
                else:
                    print(f"Error: subprocess returned non-zero exit status {return_code}", file=sys.stderr)
                    if stderr:
                        print(f"Stderr: {stderr}", file=sys.stderr)
                    sys.exit(1)
    finally:
        if os.path.exists(path):
            os.remove(path)

    return None


RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))

def build_prompt(role, **kwargs):
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
