import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
import os
import json
from unittest.mock import patch, MagicMock
from scripts import spawn_auditor
import sys

def test_auditor_artifacts_placed_in_run_dir(tmp_path, monkeypatch):
    """
    Test Case 3: When spawn_auditor.py is invoked in an environment without SDLC_RUN_DIR,
    it reads config or calculates the canonical run area, and correctly places auditor_debug/
    and auditor_verdict.json there, leaving the target workdir git status completely clean.
    """
    workdir = tmp_path / "target_repo"
    workdir.mkdir()
    
    global_dir_raw = "~/test_global_sdlc"
    resolved_global_dir = os.path.abspath(os.path.expanduser(global_dir_raw))
    
    prd_file = workdir / "PRD_Test.md"
    prd_file.write_text('1. Context & Problem (业务背景与核心痛点)\n2. Requirements & User Stories (需求定义)\n3. Architecture & Technical Strategy (架构设计与技术路线)\n4. Acceptance Criteria (BDD 黑盒验收标准)\n5. Overall Test Strategy & Quality Goal (测试策略与质量目标)\n6. Framework Modifications (框架防篡改声明)\n7. Hardcoded Content\nAffected_Projects: [leio-sdlc]\n')
    
    monkeypatch.delenv("SDLC_RUN_DIR", raising=False)
    monkeypatch.setenv("SDLC_TEST_MODE", "false")


    def side_effect_invoke(*args, **kwargs):
        expected_run_dir = os.path.join(resolved_global_dir, ".sdlc_runs", "target_repo", "PRD_Test")
        os.makedirs(expected_run_dir, exist_ok=True)
        with open(os.path.join(expected_run_dir, "auditor_verdict.json"), "w") as f:
            f.write('{"status": "APPROVED", "comments": "ok"}')
        ret = MagicMock()
        ret.stdout = '{"status": "APPROVED", "comments": "ok"}'
        return ret
    
    mock_invoke = MagicMock(side_effect=side_effect_invoke)

    
    monkeypatch.setattr(spawn_auditor, "invoke_agent", mock_invoke)
    try:
        monkeypatch.setattr(spawn_auditor.agent_driver, "send_ignition_handshake", MagicMock())
    except AttributeError:
        pass
    monkeypatch.setattr(spawn_auditor.agent_driver, "notify_channel", MagicMock())

    # Mock config
    mock_config = MagicMock()
    mock_config.get.return_value = global_dir_raw
    monkeypatch.setattr(spawn_auditor.config, "load_or_merge_config", lambda _: mock_config)

    # Run
    test_args = [
        "spawn_auditor.py",
        "--enable-exec-from-workspace",
        "--prd-file", str(prd_file),
        "--workdir", str(workdir),
        "--channel", "mock_channel"
    ]
    monkeypatch.setattr(sys, "argv", test_args)
    
    try:
        spawn_auditor.main()
    except SystemExit as e:
        assert e.code == 0
        
    expected_run_dir = os.path.join(resolved_global_dir, ".sdlc_runs", "target_repo", "PRD_Test")
    assert os.path.exists(expected_run_dir)
    assert os.path.exists(os.path.join(expected_run_dir, "auditor_verdict.json"))
    assert os.path.exists(os.path.join(expected_run_dir, "auditor_debug"))
    
    assert not os.path.exists(workdir / "auditor_debug")
    assert not os.path.exists(workdir / "auditor_verdict.json")
