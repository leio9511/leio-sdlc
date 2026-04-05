import os
import json
import tempfile
import subprocess
import time
import sys
import uuid
import shutil

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

def invoke_agent(task_string, session_key=None, role=None):
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

    fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"sdlc_prompt_{session_key}_", dir="/tmp", text=True)
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(task_string)
        
        secure_msg = f"Read your complete task instructions from {path}. Do not modify this file."
        
        # Determine LLM driver
        llm_driver = os.environ.get("LLM_DRIVER", "openclaw").lower()
        
        if llm_driver == "gemini":
            # "Uses subprocess and stdio to shell out to gemini run --model <MODEL> (or appropriate CLI flags based on LLM_DRIVER)"
            model = os.environ.get("TEST_MODEL", "google/gemini-2.0-flash")
            cmd_exec = resolve_cmd("gemini")
            cmd = [cmd_exec, "--model", model, "-p", secure_msg]
        else:
            cmd_exec = resolve_cmd("openclaw")
            cmd = [cmd_exec, "agent", "--session-id", session_key, "-m", secure_msg]
            
        print(f"[{role or 'system'}] Invoking agent driver: {' '.join(cmd)}")
        
        for attempt in range(3):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
                return session_key
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

def build_prompt(role, **kwargs):
    # Try local skill config first if we are inside a skill
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Heuristic: if we are in a deployed skill directory, scripts/ is one level down
    # Or if we are in the monorepo, we might be running from skills/<skill_name>/scripts/
    # The safest is to let the caller pass config_path or we infer it.
    
    # For now, let's look for config/prompts.json relative to the caller's directory.
    # Actually, simpler: search up the tree from the current file for config/prompts.json
    # but that will always find leio-sdlc/config/prompts.json first if agent_driver is shared.
    
    # To support dual source, let's check sys.argv[0] directory first
    caller_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    local_config_path = os.path.join(caller_dir, "..", "config", "prompts.json")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    global_config_path = os.path.join(base_dir, "config", "prompts.json")
    
    template = ""
    if os.path.exists(local_config_path):
        with open(local_config_path, "r") as f:
            prompts = json.load(f)
            template = prompts.get(role, "")
            
    if not template and os.path.exists(global_config_path):
        with open(global_config_path, "r") as f:
            prompts = json.load(f)
            template = prompts.get(role, "")
            
    for k, v in kwargs.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template

