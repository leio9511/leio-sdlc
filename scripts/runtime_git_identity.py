#!/usr/bin/env python3
import argparse
import shlex
import subprocess
import sys

AUTHORIZED_RUNTIME_GIT_ROLES = (
    "coder",
    "orchestrator",
    "merge_code",
    "commit_state",
)


def normalize_role(role):
    if role is None:
        raise ValueError("runtime git role is required")
    normalized = str(role).strip()
    if not normalized:
        raise ValueError("runtime git role is required")
    return normalized


def build_runtime_git_config(role):
    normalized_role = normalize_role(role)
    return ["-c", "sdlc.runtime=1", "-c", f"sdlc.role={normalized_role}"]


def build_runtime_git_command(role, git_args):
    if not git_args:
        raise ValueError("git arguments are required")
    return ["git", *build_runtime_git_config(role), *list(git_args)]


def run_runtime_git(role, git_args, **kwargs):
    return subprocess.run(build_runtime_git_command(role, git_args), **kwargs)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run git with the authorized SDLC runtime identity wrapper"
    )
    parser.add_argument("--role", required=True, help="Explicit SDLC runtime role")
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the fully-expanded git command instead of executing it",
    )
    parser.add_argument("git_args", nargs=argparse.REMAINDER, help="Git arguments to execute")
    args = parser.parse_args(argv)

    git_args = list(args.git_args)
    if git_args and git_args[0] == "--":
        git_args = git_args[1:]

    command = build_runtime_git_command(args.role, git_args)

    if args.print_command:
        print(shlex.join(command))
        return 0

    completed = subprocess.run(command)
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
