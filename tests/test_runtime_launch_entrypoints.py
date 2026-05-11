import importlib
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from runtime_launch_guard import is_authorized_runtime_launch


VALID_AUDITOR_PRD_CONTENT = (
    "1. Context & Problem\n"
    "2. Requirements & User Stories\n"
    "3. Architecture & Technical Strategy\n"
    "4. Acceptance Criteria\n"
    "5. Overall Test Strategy\n"
    "6. Framework Modifications\n"
    "7. Hardcoded Content"
)


def _load_module(module_name):
    module = importlib.import_module(module_name)
    return importlib.reload(module)



def test_spawn_entrypoints_accept_allowlisted_runtime_root_without_workspace_override(monkeypatch, tmp_path):
    import config

    allowed_root = tmp_path / "runtime-root" / "skills"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SDLC_TEST_MODE", "true")
    monkeypatch.setenv("MOCK_AUDIT_RESULT", "APPROVE")
    monkeypatch.setattr(config, "DEFAULT_ALLOWED_RUNTIME_ROOTS", [str(allowed_root)])

    prd_file = tmp_path / "valid_prd.md"
    prd_file.write_text(VALID_AUDITOR_PRD_CONTENT)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    spawn_auditor = _load_module("spawn_auditor")
    spawn_planner = _load_module("spawn_planner")

    with patch("runtime_launch_guard.resolve_allowed_runtime_roots", return_value=[str(allowed_root)]), \
         patch("utils_api_key.setup_spawner_api_key"), \
         patch("agent_driver.send_ignition_handshake"), \
         patch("agent_driver.notify_channel"), \
         patch.object(
             sys,
             "argv",
             [
                 str(allowed_root / "leio-sdlc" / "scripts" / "spawn_auditor.py"),
                 "--prd-file",
                 str(prd_file),
                 "--workdir",
                 str(tmp_path),
                 "--channel",
                 "stdout",
             ],
         ):
        with pytest.raises(SystemExit) as auditor_exit:
            spawn_auditor.main()
        assert auditor_exit.value.code == 0

    with patch("runtime_launch_guard.resolve_allowed_runtime_roots", return_value=[str(allowed_root)]), \
         patch("utils_api_key.setup_spawner_api_key"), \
         patch.object(
             sys,
             "argv",
             [
                 str(allowed_root / "leio-sdlc" / "scripts" / "spawn_planner.py"),
                 "--prd-file",
                 str(prd_file),
                 "--workdir",
                 str(tmp_path),
                 "--run-dir",
                 str(run_dir),
             ],
         ):
        with pytest.raises(SystemExit) as planner_exit:
            spawn_planner.main()
        assert planner_exit.value.code == 0



def test_explicit_allowed_runtime_roots_override_rejects_built_in_default_root_when_not_listed(monkeypatch, tmp_path):
    import config

    monkeypatch.setenv("HOME", str(tmp_path))
    explicit_root = tmp_path / "explicit-runtime" / "skills"
    legacy_default_root = tmp_path / ".openclaw" / "skills"
    monkeypatch.setattr(config, "DEFAULT_ALLOWED_RUNTIME_ROOTS", [str(legacy_default_root)])

    script_under_old_default = legacy_default_root / "leio-sdlc" / "scripts" / "spawn_auditor.py"

    assert not is_authorized_runtime_launch(
        str(script_under_old_default),
        app_config={config.ALLOWED_RUNTIME_ROOTS_CONFIG_KEY: [str(explicit_root)]},
    )



def test_orchestrator_and_spawn_auditor_share_identical_authorization_outcomes(monkeypatch, tmp_path):
    import config
    import orchestrator

    monkeypatch.setenv("HOME", str(tmp_path))
    allowed_root = tmp_path / ".gemini" / "skills"
    monkeypatch.setattr(config, "DEFAULT_ALLOWED_RUNTIME_ROOTS", [str(allowed_root)])

    authorized_path = str(allowed_root / "leio-sdlc" / "scripts" / "orchestrator.py")
    unauthorized_workspace_path = str(tmp_path / "workspace" / "scripts" / "spawn_auditor.py")

    assert orchestrator.is_authorized_runtime_launch(authorized_path)
    assert is_authorized_runtime_launch(authorized_path)
    assert not orchestrator.is_authorized_runtime_launch(unauthorized_workspace_path)
    assert not is_authorized_runtime_launch(unauthorized_workspace_path)
