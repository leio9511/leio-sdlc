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

def is_case1_strict_mode() -> bool:
    """Return True only when the resolved continuity mode is 'case1_strict'.

    This is the single observation point that downstream PRs will use to
    gate case-1 strong-continuity behaviour.  It is purely an observer — it
    must NOT introduce any behaviour changes to the existing invoke path.
    """
    from config import get_continuity_mode
    return get_continuity_mode() == "case1_strict"


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

def invoke_agent(task_string, session_key=None, role=None, run_dir=None, thinking: str | None = None):
    """
    Core router that dynamically selects the CLI driver and flags based on the active LLM_DRIVER.
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
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", actual_id, "--thinking", resolved_thinking, "-m", secure_msg]
            else:
                cmd = [cmd_exec, "agent", "--agent", agent_id, "--session-id", session_key, "--thinking", resolved_thinking, "-m", secure_msg]
            
        print(f"[{role or 'system'}] Invoking agent driver: {' '.join(cmd)}")
        
        for attempt in range(3):
            # Native inheritance: Ensure GEMINI_API_KEY is natively inherited for stateless execution
            run_env = os.environ.copy()
            if os.environ.get("GEMINI_API_KEY"):
                run_env["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY")

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
                    return_code = process.wait()

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


# ── Bootstrap artifact integration (PR-002) ─────────────────────────────
# Thin convenience layer on top of bootstrap_artifact that exposes
# the artifact lifecycle to the agent-driver runtime.  All schema and
# classification logic lives in bootstrap_artifact.py.
#
# Imports are lazy (per-function) to avoid breaking sandboxed deployment
# copies that may not include bootstrap_artifact.py alongside agent_driver.


def ensure_bootstrap_dir(run_dir: str) -> str:
    """Ensure the bootstrap artifact directory exists and return its path."""
    from bootstrap_artifact import get_bootstrap_dir
    bd = get_bootstrap_dir(run_dir)
    os.makedirs(bd, exist_ok=True)
    return bd


def record_bootstrap_success(
    run_dir: str,
    invocation_id: str,
    engine: str,
    resume_handle: str,
    resume_kind: str,
    source: str = "cli_runtime",
    captured_at: str | None = None,
) -> str:
    """Record a successful Phase-1 bootstrap and return the artifact path.

    Convenience wrapper around ``bootstrap_artifact.write_bootstrap_success``.
    """
    from bootstrap_artifact import write_bootstrap_success
    return write_bootstrap_success(
        run_dir=run_dir,
        invocation_id=invocation_id,
        engine=engine,
        resume_handle=resume_handle,
        resume_kind=resume_kind,
        source=source,
        captured_at=captured_at,
    )


def record_bootstrap_failure(
    run_dir: str,
    invocation_id: str,
    engine: str,
    failure_reason: str = "missing_authoritative_resume_handle",
) -> str:
    """Record a failed Phase-1 bootstrap and return the artifact path.

    Convenience wrapper around ``bootstrap_artifact.write_bootstrap_failure``.
    """
    from bootstrap_artifact import write_bootstrap_failure
    return write_bootstrap_failure(
        run_dir=run_dir,
        invocation_id=invocation_id,
        engine=engine,
        failure_reason=failure_reason,
    )


def record_bootstrap_index(run_dir: str, active_targets: dict) -> str:
    """Write the bootstrap index artifact.

    Convenience wrapper around ``bootstrap_artifact.write_bootstrap_index``.
    """
    from bootstrap_artifact import write_bootstrap_index
    return write_bootstrap_index(run_dir=run_dir, active_targets=active_targets)


def is_eligible_for_strong_continuity(run_dir: str, invocation_id: str) -> bool:
    """Check whether a bootstrap artifact authorises strong continuity.

    Returns True only when the artifact exists, ``ok`` is True, and
    ``authoritative`` is True.
    """
    from bootstrap_artifact import read_bootstrap_artifact, is_bootstrap_successful
    try:
        artifact = read_bootstrap_artifact(run_dir, invocation_id)
        return is_bootstrap_successful(artifact)
    except FileNotFoundError:
        return False


# ── Two-Phase Bootstrap / Continue Protocol (PR-003) ───────────────────
# Phase 1: establish a minimal session and capture an authoritative resume
# identifier.  Phase 2: resume that session with the full task envelope.
#
# The existing invoke_agent() single-phase path is preserved unchanged.


def build_bootstrap_prompt() -> str:
    """Return an ultra-thin bootstrap prompt for Phase 1 session establishment.

    The prompt must:
    - Establish a minimal session (no real business task)
    - NOT include any role declaration, reference index, execution contract,
      or final checklist
    - NOT inject the full main task envelope
    - Be as short as possible while still being a valid engine invocation
    - Use exactly the labels from PRD section 7
    """
    return "Phase 1: bootstrap\nPhase 2: continue\n"


def capture_gemini_session_id(cmd_exec: str, prompt_tempfile_path: str) -> str | None:
    """Attempt to capture an authoritative session id from the Gemini CLI.

    After Phase 1 bootstrap with Gemini, this function queries the Gemini CLI
    for the session id using an authoritative capture path.  It **must not**
    fall back to ``--list-sessions`` text parsing, ``latest`` inference, or
    prompt-preview matching.

    Returns a session id string on success, or ``None`` if no authoritative
    capture path is available (indicating bootstrap failure).
    """
    # The Gemini CLI does not currently expose a machine-readable session-id
    # return mechanism after invocation.  ``--list-sessions -o json`` produces
    # text-format output, not structured JSON suitable for authoritative
    # identity binding.  Per PRD section 3.4, textual session-list output is
    # not an authoritative source.
    #
    # When Gemini CLI adds a structured session-id output (e.g. a JSON event
    # stream with a session-created message), this function should be updated
    # to consume it.
    return None


def invoke_agent_two_phase(
    task_string,
    session_key=None,
    role=None,
    run_dir=None,
    thinking=None,
):
    """Two-phase bootstrap/continue protocol for non-OpenClaw engines.

    **Phase 1 — Bootstrap:**
    1. Build and send the ultra-thin bootstrap prompt via the Gemini CLI
    2. Capture the authoritative session id
    3. Write a bootstrap success or failure artifact
    4. Write the bootstrap index artifact

    **Phase 2 — Continue:**
    1. Verify the bootstrap artifact signals success
    2. Resume the engine session with ``--resume <session_id>`` and the
       **full** *task_string* envelope
    3. If bootstrap failed, return ``AgentResult`` with ``return_code=1``

    The existing ``invoke_agent()`` single-phase path is unchanged.
    """
    import uuid

    if not session_key:
        session_key = f"subtask-{uuid.uuid4().hex[:8]}"

    invocation_id = f"{session_key}_{uuid.uuid4().hex[:8]}"
    engine = os.environ.get("LLM_DRIVER", "openclaw").lower()

    # ── Resolve temp directory ──────────────────────────────────────────
    if run_dir and os.path.exists(run_dir):
        temp_dir = os.path.join(run_dir, ".tmp")
    else:
        temp_dir = tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)

    # ── Ensure bootstrap artifact directory exists ──────────────────────
    if run_dir:
        ensure_bootstrap_dir(run_dir)

    # ── Phase 1: Bootstrap ──────────────────────────────────────────────
    bootstrap_prompt = build_bootstrap_prompt()

    fd, bootstrap_prompt_path = tempfile.mkstemp(
        suffix=".txt", prefix=f"sdlc_bootstrap_{session_key}_",
        dir=temp_dir, text=True,
    )
    try:
        os.chmod(bootstrap_prompt_path, 0o600)
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(bootstrap_prompt)

        cmd_exec = resolve_cmd("gemini")
        run_env = os.environ.copy()

        # ── Mock bootstrap: short-circuit Phase 1 for test environments ─
        if "SDLC_MOCK_LLM_RESPONSE" in os.environ:
            mock_session_id = os.environ.get("SDLC_MOCK_SESSION_ID")
            if mock_session_id:
                record_bootstrap_success(
                    run_dir=run_dir,
                    invocation_id=invocation_id,
                    engine=engine,
                    resume_handle=mock_session_id,
                    resume_kind="session_id",
                )
            else:
                record_bootstrap_failure(
                    run_dir=run_dir,
                    invocation_id=invocation_id,
                    engine=engine,
                )
            record_bootstrap_index(
                run_dir=run_dir,
                active_targets={session_key: f"bootstrap/{invocation_id}.json"},
            )

            if not mock_session_id:
                return AgentResult(
                    session_key=session_key,
                    stdout="",
                    stderr="bootstrap failure: missing_authoritative_resume_handle",
                    return_code=1,
                )

            captured_id = mock_session_id
        else:
            # ── Real Phase 1 execution ──────────────────────────────────
            secure_msg = (
                f"Read your complete task instructions from {bootstrap_prompt_path}. "
                f"Do not modify this file."
            )
            cmd = [cmd_exec, "--yolo", "-p", secure_msg]

            print(f"[{role or 'system'}] Phase 1 bootstrap: {' '.join(cmd)}")

            process1 = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=run_env,
            )
            process1.wait()

            captured_id = capture_gemini_session_id(cmd_exec, bootstrap_prompt_path)

            if captured_id:
                record_bootstrap_success(
                    run_dir=run_dir,
                    invocation_id=invocation_id,
                    engine=engine,
                    resume_handle=captured_id,
                    resume_kind="session_id",
                )
            else:
                record_bootstrap_failure(
                    run_dir=run_dir,
                    invocation_id=invocation_id,
                    engine=engine,
                )

            record_bootstrap_index(
                run_dir=run_dir,
                active_targets={session_key: f"bootstrap/{invocation_id}.json"},
            )

            if not captured_id:
                return AgentResult(
                    session_key=session_key,
                    stdout="",
                    stderr="bootstrap failure: missing_authoritative_resume_handle",
                    return_code=1,
                )

        # ── Phase 2: Continue ───────────────────────────────────────────
        fd2, phase2_prompt_path = tempfile.mkstemp(
            suffix=".txt", prefix=f"sdlc_phase2_{session_key}_",
            dir=temp_dir, text=True,
        )
        try:
            os.chmod(phase2_prompt_path, 0o600)
            with os.fdopen(fd2, 'w') as tmp:
                tmp.write(task_string)

            secure_msg2 = (
                f"Read your complete task instructions from {phase2_prompt_path}. "
                f"Do not modify this file."
            )
            cmd2 = [cmd_exec, "--yolo", "-p", secure_msg2, "-r", captured_id]

            print(
                f"[{role or 'system'}] Phase 2 continue: "
                f"{' '.join(c for c in cmd2 if c != secure_msg2)}"
            )

            stdout_fd, stdout_path = tempfile.mkstemp(
                prefix=f"sdlc_stdout_{session_key}_", dir=temp_dir, text=True,
            )
            stderr_fd, stderr_path = tempfile.mkstemp(
                prefix=f"sdlc_stderr_{session_key}_", dir=temp_dir, text=True,
            )
            os.close(stdout_fd)
            os.close(stderr_fd)

            try:
                with open(stdout_path, "w") as stdout_file, \
                     open(stderr_path, "w") as stderr_file:
                    process2 = subprocess.Popen(
                        cmd2,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        start_new_session=True,
                        env=run_env,
                    )
                    return_code = process2.wait()

                with open(stdout_path, "r") as stdout_file:
                    stdout = stdout_file.read()
                with open(stderr_path, "r") as stderr_file:
                    stderr = stderr_file.read()
            finally:
                for p in (stdout_path, stderr_path):
                    try:
                        os.remove(p)
                    except (FileNotFoundError, OSError):
                        pass

            return AgentResult(
                session_key=session_key,
                stdout=stdout,
                stderr=stderr,
                return_code=return_code,
            )
        finally:
            try:
                os.remove(phase2_prompt_path)
            except (FileNotFoundError, OSError):
                pass
    finally:
        try:
            os.remove(bootstrap_prompt_path)
        except (FileNotFoundError, OSError):
            pass


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
