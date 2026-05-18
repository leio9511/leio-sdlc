#!/usr/bin/env python3
"""Official no-side-effect runtime smoke entrypoint for leio-sdlc.

Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation.
"""

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_launch_guard

SMOKE_POLICY = "Use a minimal, no-side-effect official smoke path that proves interpreter binding, key imports, and startup-path initialization. Do not use full auditor/orchestrator/long-running business execution as default smoke validation."


def _import_key_dependencies():
    imported = []

    import yaml  # PyYAML

    imported.append(f"yaml:{getattr(yaml, '__version__', 'unknown')}")

    import config

    imported.append("config")

    import utils_json

    imported.append("utils_json")
    imported.append("runtime_launch_guard")
    return imported


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Official minimal no-side-effect leio-sdlc runtime smoke path.",
        epilog=SMOKE_POLICY,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--skill-root",
        default=None,
        help=(
            "Expected deployed leio-sdlc skill root. When provided without "
            "--expected-runtime-python, the smoke requires <skill-root>/.venv/bin/python. "
            "May also be supplied via LEIO_SDLC_SKILL_ROOT."
        ),
    )
    parser.add_argument(
        "--expected-runtime-python",
        default=None,
        help=(
            "Expected runtime Python interpreter path. Overrides --skill-root. "
            "May also be supplied via LEIO_SDLC_RUNTIME_PYTHON."
        ),
    )
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        expected_python = runtime_launch_guard.validate_runtime_interpreter(
            skill_root=args.skill_root,
            expected_python=args.expected_runtime_python,
            script_path=__file__,
        )
    except runtime_launch_guard.RuntimeInterpreterMismatch as exc:
        print(f"runtime smoke failed: {exc}", file=sys.stderr)
        return 1

    imported = _import_key_dependencies()
    runtime_skill_root = runtime_launch_guard.resolve_skill_root_for_runtime_smoke(
        skill_root=args.skill_root,
        expected_python=args.expected_runtime_python,
        script_path=__file__,
    )
    print(
        "runtime smoke ok: "
        f"python={runtime_launch_guard._canonicalize_path(sys.executable)}; "
        f"expected={expected_python}; "
        f"skill_root={runtime_skill_root}; "
        f"startup_path={runtime_launch_guard._canonicalize_path(SCRIPT_DIR)}; "
        f"imports={', '.join(imported)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
