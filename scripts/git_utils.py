import subprocess
import logging

class GitCheckoutError(Exception):
    pass

def safe_git_checkout(branch_name, create=False):
    """
    Safely executes git checkout operations.
    Raises GitCheckoutError on failure without running destructive commands.
    """
    cmd = ["git", "checkout"]
    if create:
        cmd.append("-b")
    cmd.append(branch_name)

    try:
        # Wrap the subprocess call for git checkout in a try...except block
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result
    except subprocess.CalledProcessError as e:
        error_msg = f"Git checkout failed for branch '{branch_name}'. Error: {e.stderr}"
        logging.error(error_msg)
        raise GitCheckoutError(error_msg) from e

def check_git_boundary(workdir):
    import os
    import sys
    import subprocess
    if not os.path.exists(os.path.join(workdir, ".git")):
        print(f"[FATAL] Git boundary violation: workdir '{workdir}' must contain a .git directory.")
        sys.exit(1)
    
    toplevel = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, cwd=workdir).stdout.strip()
    if os.path.abspath(toplevel) != os.path.abspath(workdir):
        print(f"[FATAL] Git boundary violation: workdir '{workdir}' is not the root of the git repository.")
        sys.exit(1)
