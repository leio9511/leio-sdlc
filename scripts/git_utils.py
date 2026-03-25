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
