import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from notification_formatter import format_notification

def test_format_sdlc_handshake():
    res = format_notification("sdlc_handshake", {})
    assert res == "🤝 [SDLC Engine] Initial Handshake successful. Channel linked."

def test_auditor_start_with_command():
    res = format_notification("auditor_start", {
        "prd_file": "PRD_081_test.md",
        "command": "python3 spawn_auditor.py PRD_081_test.md"
    })
    expected = "🚀 [Auditor] Starting PRD audit for: PRD_081_test.md\n💻 Command: `python3 spawn_auditor.py PRD_081_test.md`"
    assert res == expected

def test_auditor_start_without_command():
    # Absent
    res = format_notification("auditor_start", {"prd_file": "PRD_081_test.md"})
    assert res == "🚀 [Auditor] Starting PRD audit for: PRD_081_test.md"
    
    # Empty
    res_empty = format_notification("auditor_start", {"prd_file": "PRD_081_test.md", "command": ""})
    assert res_empty == "🚀 [Auditor] Starting PRD audit for: PRD_081_test.md"

def test_format_slicing_start():
    res = format_notification("slicing_start", {"prd_id": "PRD_081_test.md"})
    assert res == "🔪 [Planner] Slicing PRD into Micro-PRs..."

def test_format_slicing_end():
    res = format_notification("slicing_end", {"prd_id": "PRD_081_test.md", "count": 5})
    assert res == "✅ [Planner] Slicing complete. 5 PRs generated."

def test_format_coder_spawned():
    res = format_notification("coder_spawned", {"pr_id": "PR_001_test.md"})
    assert res == "💻 [Coder] Implementing pr-001..."

def test_format_reviewer_spawned():
    res = format_notification("reviewer_spawned", {"pr_id": "PR_001_test.md"})
    assert res == "🔍 [Reviewer] Auditing changes for pr-001..."

def test_format_pr_merged():
    res = format_notification("pr_merged", {"pr_id": "PR_001_test.md"})
    assert res == "✅ [Merge] pr-001 merged to master."

def test_format_uat_start():
    res = format_notification("uat_start", {"prd_id": "PRD_123_Test.md"})
    assert res == "🧪 [UAT] Starting final verification..."

def test_format_notification_uses_issue_1166_templates():
    # Specific test case required by PR-002
    assert format_notification("sdlc_handshake", {}) == "🤝 [SDLC Engine] Initial Handshake successful. Channel linked."
    assert format_notification("auditor_start", {"prd_file": "test.md"}) == "🚀 [Auditor] Starting PRD audit for: test.md"
    assert format_notification("slicing_start", {}) == "🔪 [Planner] Slicing PRD into Micro-PRs..."
    assert format_notification("slicing_end", {"count": 3}) == "✅ [Planner] Slicing complete. 3 PRs generated."
    assert format_notification("coder_spawned", {"pr_id": "pr-123"}) == "💻 [Coder] Implementing pr-123..."
    assert format_notification("reviewer_spawned", {"pr_id": "pr-123"}) == "🔍 [Reviewer] Auditing changes for pr-123..."
    assert format_notification("pr_merged", {"pr_id": "pr-123"}) == "✅ [Merge] pr-123 merged to master."
    assert format_notification("uat_start", {}) == "🧪 [UAT] Starting final verification..."

