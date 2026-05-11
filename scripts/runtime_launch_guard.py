#!/usr/bin/env python3
import os

import config


def _canonicalize_path(path):
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


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
