import os
from pathlib import Path

def get_repo_python() -> str:
    """
    Returns the absolute path to the repository's explicit .venv/bin/python interpreter.
    This acts as the Python-side adapter of the scripts/dev_python.sh contract,
    ensuring subprocesses do not drift into ambient host python3 execution.
    """
    repo_root = Path(__file__).resolve().parent.parent
    python_bin = repo_root / ".venv" / "bin" / "python"
    
    if not python_bin.exists():
        raise FileNotFoundError(f"Repository python interpreter not found at {python_bin}. "
                                "Ensure the environment is bootstrapped.")
        
    return str(python_bin)
