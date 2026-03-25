# PR Contract: ISSUE-020 (Refactor CUJ-5: Update Issue)

## Overview
This PR contract outlines the exact implementation details for Refactoring SDLC CUJ-5 (Update Issue Tracking) for Testability. The goal is to replace direct file edits for issue updates with a dedicated Python wrapper (`update_issue.py`) to support "Zero Side-Effect Automated Testing" via a "Limb Stubbing" architecture.

**Target Files to Create/Modify:**
1. `scripts/update_issue.py`
2. `SKILL.md`
3. `scripts/test_cuj_5_mock.sh`

## Acceptance Criteria (AC)

### 1. Implement `scripts/update_issue.py`
You must create `scripts/update_issue.py` with the following exact specifications:
- **Inputs**: Use `argparse` to accept exactly `--issue-id <ID>` (e.g., `ISSUE-012`) and `--status <status>` (e.g., `closed`, `in-progress`).
- **Test Mode (`SDLC_TEST_MODE=true`)**:
  - Do NOT modify any `.issues/*.md` files.
  - Append the exact string to `tests/tool_calls.log`: `{'tool': 'update_issue', 'args': {'issue_id': <ID>, 'status': <status>}}` (You must use Python dict to string conversion `str({...})` to ensure it formats with single quotes).
  - Print exactly `{"status": "mock_success", "action": "update_issue"}` to stdout.
  - Exit with code `0`.
- **Production Mode**:
  - Locate the target file `.issues/<ID>.md`.
  - Open the file, find the line starting with `status:`, and replace the status with the new `<status>` using regex replacement (e.g., replace `status: xxx` with `status: <status>`).
  - If the target markdown file does not exist, print an error message and exit with code `1`.
  - Save the file and print a success message, ensuring no other content in the markdown file is corrupted.

### 2. Update `SKILL.md`
You must modify `SKILL.md` to update Command Template 5.
- Locate Command Template 5 (Issue Tracking) in `SKILL.md`.
- Replace the instructions that tell the agent to "use the edit tool" with the following **exact literal string**:
  `To update an issue status, use the \`exec\` tool to run: \`python scripts/update_issue.py --issue-id <ID> --status <new_status>\``

### 3. Implement `scripts/test_cuj_5_mock.sh`
You must create the End-to-End Mock verification script `scripts/test_cuj_5_mock.sh` with the following requirements:
- Set `export SDLC_TEST_MODE=true`.
- Execute the real OpenClaw agent exactly as follows: 
  `openclaw agent -m "功能已经开发完了并且合并到 master 了，请把 ISSUE-999 的状态更新为 closed"`
- Include an assertion step that runs exactly: `grep -q "'tool': 'update_issue'" tests/tool_calls.log` and ensures it succeeds.

---
**Note to Coder**: This contract is self-contained. All exact log formats, file modification logic details, and string replacements are fully specified above. Do not deviate from the single-quote log formatting or the exact `SKILL.md` replacement text.