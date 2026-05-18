#!/usr/bin/env python3
import os
import sys

import config

SKILL_ROOT_ENV_VAR = "LEIO_SDLC_SKILL_ROOT"
EXPECTED_RUNTIME_PYTHON_ENV_VAR = "LEIO_SDLC_RUNTIME_PYTHON"
RUNTIME_EXECUTION_CONTEXT_DESCRIPTION = (
    "deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap"
)


class RuntimeInterpreterMismatch(RuntimeError):
    """Raised when a runtime launch uses an unexpected Python interpreter."""


def _canonicalize_path(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(os.fspath(path))))


def resolve_runtime_skill_root(skill_root=None, script_path=None, env=None):
    """Resolve the deployed skill root used for runtime interpreter binding.

    Caller-supplied skill roots take precedence over environment configuration.
    Otherwise derive the root from a script path under ``<skill-root>/scripts/``.
    """
    if env is None:
        env = os.environ

    configured_skill_root = skill_root or env.get(SKILL_ROOT_ENV_VAR)
    if configured_skill_root:
        return _canonicalize_path(configured_skill_root)

    runtime_script_path = script_path or __file__
    scripts_dir = os.path.dirname(_canonicalize_path(runtime_script_path))
    return _canonicalize_path(os.path.dirname(scripts_dir))


def runtime_python_for_skill_root(skill_root):
    """Return canonical ``<skill-root>/.venv/bin/python`` for a deployed skill root."""
    return _canonicalize_path(os.path.join(skill_root, ".venv", "bin", "python"))


def resolve_expected_runtime_python(
    skill_root=None,
    expected_python=None,
    script_path=None,
    env=None,
):
    """Resolve the expected runtime Python interpreter for the skill root."""
    if env is None:
        env = os.environ

    configured_expected_python = expected_python or env.get(EXPECTED_RUNTIME_PYTHON_ENV_VAR)
    if configured_expected_python:
        return _canonicalize_path(configured_expected_python)

    resolved_skill_root = resolve_runtime_skill_root(
        skill_root=skill_root,
        script_path=script_path,
        env=env,
    )
    return runtime_python_for_skill_root(resolved_skill_root)


def resolve_skill_root_for_runtime_smoke(skill_root=None, expected_python=None, script_path=None, env=None):
    """Resolve the skill root reported by the runtime smoke contract."""
    if skill_root:
        return resolve_runtime_skill_root(skill_root=skill_root, script_path=script_path, env=env)

    resolved_expected = resolve_expected_runtime_python(
        expected_python=expected_python,
        script_path=script_path,
        env=env,
    )
    expected_parts = resolved_expected.split(os.sep)
    if len(expected_parts) >= 4 and expected_parts[-3:] == [".venv", "bin", "python"]:
        return os.sep.join(expected_parts[:-3]) or os.sep

    return resolve_runtime_skill_root(script_path=script_path, env=env)


def validate_runtime_interpreter(
    actual_python=None,
    expected_python=None,
    skill_root=None,
    script_path=None,
    env=None,
):
    """Validate that the active interpreter is the expected runtime interpreter.

    Returns the canonical expected interpreter path when validation succeeds and
    raises ``RuntimeInterpreterMismatch`` with actual/expected paths otherwise.
    """
    canonical_actual = _canonicalize_path(actual_python or sys.executable)
    canonical_expected = resolve_expected_runtime_python(
        skill_root=skill_root,
        expected_python=expected_python,
        script_path=script_path,
        env=env,
    )

    if canonical_actual != canonical_expected:
        raise RuntimeInterpreterMismatch(
            "Runtime Python interpreter mismatch for "
            f"{RUNTIME_EXECUTION_CONTEXT_DESCRIPTION}: "
            f"actual={canonical_actual}; expected={canonical_expected}"
        )

    return canonical_expected


def resolve_allowed_runtime_roots(app_config=None):
    if app_config is None:
        runtime_dir = os.path.dirname(os.path.abspath(__file__))
        sdlc_root = os.path.dirname(runtime_dir)
        app_config = config.load_or_merge_config(sdlc_root)

    configured_roots = config.get_allowed_runtime_roots(app_config)
    roots = configured_roots if configured_roots is not None else config.DEFAULT_ALLOWED_RUNTIME_ROOTS
    return [_canonicalize_path(root) for root in roots]


def is_authorized_runtime_launch(script_path, allowed_roots=None, app_config=None):
    if allowed_roots is None:
        allowed_roots = resolve_allowed_runtime_roots(app_config=app_config)

    canonical_script_path = _canonicalize_path(script_path)
    canonical_allowed_roots = [_canonicalize_path(root) for root in allowed_roots]
    for allowed_root in canonical_allowed_roots:
        if os.path.commonpath([canonical_script_path, allowed_root]) == allowed_root:
            return True
    return False
