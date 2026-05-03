"""Focused automated coverage for allowlisted roles, blocked roles, and missing-role fail-closed behavior.

PR-002: Role-Aware Runtime Hook Allowlist Enforcement
"""
import os
import subprocess
import sys
import shutil
from pathlib import Path

import pytest

HOOK_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".sdlc_hooks",
    "pre-commit",
)


def _setup_sandbox(tmp_path):
    """Create a temp git repo on master with .sdlc_guardrail and the managed hook installed."""
    os.chdir(str(tmp_path))
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

    # Create guardrail file
    (tmp_path / ".sdlc_guardrail").write_text("")
    subprocess.run(["git", "add", ".sdlc_guardrail"], check=True)
    subprocess.run(["git", "commit", "-m", "init"], check=True)

    # Install the SDLC managed hook
    hooks_dir = tmp_path / ".sdlc_hooks"
    hooks_dir.mkdir(exist_ok=True)
    shutil.copy(HOOK_SOURCE, hooks_dir / "pre-commit")
    subprocess.run(["git", "config", "core.hooksPath", ".sdlc_hooks"], check=True)


@pytest.mark.parametrize(
    "role,expect_pass",
    [
        ("coder", True),
        ("orchestrator", True),
        ("merge_code", True),
        ("commit_state", True),
        ("verifier", False),
        ("reviewer", False),
        ("auditor", False),
        ("planner", False),
        ("arbitrator", False),
        ("unknown", False),
    ],
)
def test_runtime_role_hook_authorization(tmp_path, role, expect_pass):
    """Verify allowlisted roles pass the hook and non-allowlisted roles are blocked."""
    _setup_sandbox(tmp_path)

    # Create a test file to commit
    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        [
            "git",
            "-c", "sdlc.runtime=1",
            "-c", f"sdlc.role={role}",
            "commit", "-m", f"test: runtime commit as {role}",
        ],
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr

    if expect_pass:
        assert result.returncode == 0, f"Authorized role '{role}' was blocked: {combined}"
    else:
        assert result.returncode == 1, f"Unauthorized role '{role}' was NOT blocked"
        assert (
            f"❌ Commit rejected: SDLC runtime role '{role}' is not authorized to commit."
            in combined
        ), f"Wrong rejection message for '{role}': {combined}"


def test_runtime_commit_with_missing_role_is_rejected(tmp_path):
    """sdlc.runtime=1 without sdlc.role fails and emits the exact missing-role message."""
    _setup_sandbox(tmp_path)

    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        [
            "git",
            "-c", "sdlc.runtime=1",
            "commit", "-m", "runtime commit without role",
        ],
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"Missing role commit was NOT blocked: {combined}"
    assert (
        "❌ Commit rejected: runtime commit requires explicit sdlc.role."
        in combined
    ), f"Missing exact rejection message. Got: {combined}"


def test_runtime_commit_with_verifier_role_is_rejected(tmp_path):
    """Protected-branch runtime commit with sdlc.role=verifier fails with exact unauthorized message."""
    _setup_sandbox(tmp_path)

    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        [
            "git",
            "-c", "sdlc.runtime=1",
            "-c", "sdlc.role=verifier",
            "commit", "-m", "runtime commit as verifier",
        ],
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"Verifier role commit was NOT blocked: {combined}"
    assert (
        "❌ Commit rejected: SDLC runtime role 'verifier' is not authorized to commit."
        in combined
    ), f"Missing exact rejection message. Got: {combined}"


def test_runtime_commit_with_authorized_roles_is_allowed(tmp_path):
    """Representative allowlisted roles (coder, merge_code, commit_state) are not blocked."""
    for role in ("coder", "merge_code", "commit_state"):
        # Create a fresh sandbox for each role to keep independent commits
        role_dir = tmp_path / role
        role_dir.mkdir()
        _setup_sandbox(role_dir)

        (role_dir / f"{role}_test.txt").write_text(role)
        subprocess.run(["git", "add", f"{role}_test.txt"], check=True)

        result = subprocess.run(
            [
                "git",
                "-c", "sdlc.runtime=1",
                "-c", f"sdlc.role={role}",
                "commit", "-m", f"test: runtime commit as {role}",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Authorized role '{role}' was blocked: {result.stdout + result.stderr}"
        )


def test_non_runtime_direct_commit_still_blocked(tmp_path):
    """Direct commit on protected branch without runtime bypass is still rejected."""
    _setup_sandbox(tmp_path)

    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        ["git", "commit", "-m", "direct commit"],
        capture_output=True,
        text=True,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1, f"Direct commit was NOT blocked: {combined}"
    assert "GIT COMMIT REJECTED" in combined, f"Missing rejection banner. Got: {combined}"


def test_non_protected_branch_commit_still_allowed(tmp_path):
    """Commits on feature branches are not intercepted by the protected-branch logic."""
    _setup_sandbox(tmp_path)

    # Switch to a feature branch
    subprocess.run(["git", "checkout", "-b", "feature/test"], check=True)

    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        ["git", "commit", "-m", "feature commit"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Feature branch commit was blocked: {result.stdout + result.stderr}"
    )


def test_sdlc_override_bypasses_hook(tmp_path):
    """sdlc.override=true bypasses the hook entirely (glass-break path)."""
    _setup_sandbox(tmp_path)

    (tmp_path / "test.txt").write_text("content")
    subprocess.run(["git", "add", "test.txt"], check=True)

    result = subprocess.run(
        [
            "git",
            "-c", "sdlc.override=true",
            "commit", "-m", "override commit",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Override commit was blocked: {result.stdout + result.stderr}"
    )
