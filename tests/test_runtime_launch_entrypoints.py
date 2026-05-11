import importlib
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


VALID_AUDITOR_PRD_CONTENT = (
    "1. Context & Problem\n"
    "2. Requirements & User Stories\n"
    "3. Architecture & Technical Strategy\n"
    "4. Acceptance Criteria\n"
    "5. Overall Test Strategy\n"
    "6. Framework Modifications\n"
    "7. Hardcoded Content"
)


class _StartupAllowed(BaseException):
    pass


def _load_module(module_name):
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def _runtime_overlay(allowed_roots):
    return {
        "ALLOWED_RUNTIME_ROOTS": [str(root) for root in allowed_roots],
        "GLOBAL_RUN_DIR": "",
    }


def _spawn_auditor_startup_outcome(script_path, tmp_path, allowed_roots):
    spawn_auditor = _load_module("spawn_auditor")
    prd_file = tmp_path / "valid_prd.md"
    prd_file.write_text(VALID_AUDITOR_PRD_CONTENT)

    with patch("runtime_launch_guard.config.load_or_merge_config", return_value=_runtime_overlay(allowed_roots)), \
         patch("utils_api_key.setup_spawner_api_key"), \
         patch("agent_driver.send_ignition_handshake", side_effect=_StartupAllowed), \
         patch("handoff_prompter.HandoffPrompter.get_prompt", return_value="startup blocked"), \
         patch.object(
             sys,
             "argv",
             [
                 str(script_path),
                 "--prd-file",
                 str(prd_file),
                 "--workdir",
                 str(tmp_path),
                 "--channel",
                 "stdout",
             ],
         ):
        try:
            spawn_auditor.main()
        except _StartupAllowed:
            return "allowed"
        except SystemExit as exc:
            assert exc.code == 1
            return "blocked"

    raise AssertionError("spawn_auditor.main() returned without a startup outcome")


def _spawn_planner_startup_outcome(script_path, tmp_path, allowed_roots):
    spawn_planner = _load_module("spawn_planner")
    prd_file = tmp_path / "valid_prd.md"
    prd_file.write_text(VALID_AUDITOR_PRD_CONTENT)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)

    with patch("runtime_launch_guard.config.load_or_merge_config", return_value=_runtime_overlay(allowed_roots)), \
         patch("utils_api_key.setup_spawner_api_key"), \
         patch("spawn_planner.os.chdir", side_effect=_StartupAllowed), \
         patch("handoff_prompter.HandoffPrompter.get_prompt", return_value="startup blocked"), \
         patch.object(
             sys,
             "argv",
             [
                 str(script_path),
                 "--prd-file",
                 str(prd_file),
                 "--workdir",
                 str(tmp_path),
                 "--run-dir",
                 str(run_dir),
             ],
         ):
        try:
            spawn_planner.main()
        except _StartupAllowed:
            return "allowed"
        except SystemExit as exc:
            assert exc.code == 1
            return "blocked"

    raise AssertionError("spawn_planner.main() returned without a startup outcome")


def _orchestrator_startup_outcome(script_path, tmp_path, allowed_roots):
    orchestrator = _load_module("orchestrator")

    with patch("runtime_launch_guard.config.load_or_merge_config", return_value=_runtime_overlay(allowed_roots)), \
         patch("orchestrator.load_or_merge_config", side_effect=_StartupAllowed), \
         patch("handoff_prompter.HandoffPrompter.get_prompt", return_value="startup blocked"), \
         patch.object(
             sys,
             "argv",
             [
                 str(script_path),
                 "--workdir",
                 str(tmp_path),
                 "--prd-file",
                 str(tmp_path / "dummy.md"),
                 "--force-replan",
                 "true",
             ],
         ):
        try:
            orchestrator.main()
        except _StartupAllowed:
            return "allowed"
        except SystemExit as exc:
            assert exc.code == 1
            return "blocked"

    raise AssertionError("orchestrator.main() returned without a startup outcome")


def test_spawn_entrypoints_accept_allowlisted_runtime_root_without_workspace_override(tmp_path):
    allowed_root = tmp_path / "runtime-root" / "skills"
    authorized_script_path = allowed_root / "leio-sdlc" / "scripts" / "entrypoint.py"

    assert _spawn_auditor_startup_outcome(authorized_script_path, tmp_path, [allowed_root]) == "allowed"
    assert _spawn_planner_startup_outcome(authorized_script_path, tmp_path, [allowed_root]) == "allowed"


def test_explicit_allowed_runtime_roots_override_rejects_built_in_default_root_when_not_listed(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    explicit_root = tmp_path / "explicit-runtime" / "skills"
    built_in_default_script_path = tmp_path / ".openclaw" / "skills" / "leio-sdlc" / "scripts" / "spawn_auditor.py"

    assert _spawn_auditor_startup_outcome(built_in_default_script_path, tmp_path, [explicit_root]) == "blocked"


def test_orchestrator_and_spawn_auditor_share_identical_authorization_outcomes(tmp_path):
    allowed_root = tmp_path / ".gemini" / "skills"
    authorized_script_path = allowed_root / "leio-sdlc" / "scripts" / "entrypoint.py"
    unauthorized_workspace_script_path = tmp_path / "workspace" / "leio-sdlc" / "scripts" / "entrypoint.py"

    assert _orchestrator_startup_outcome(authorized_script_path, tmp_path, [allowed_root]) == "allowed"
    assert _spawn_auditor_startup_outcome(authorized_script_path, tmp_path, [allowed_root]) == "allowed"

    assert _orchestrator_startup_outcome(unauthorized_workspace_script_path, tmp_path, [allowed_root]) == "blocked"
    assert _spawn_auditor_startup_outcome(unauthorized_workspace_script_path, tmp_path, [allowed_root]) == "blocked"
