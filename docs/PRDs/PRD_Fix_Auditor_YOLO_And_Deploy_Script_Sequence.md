---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix_Auditor_YOLO_And_Deploy_Script_Sequence

## 1. Context & Problem (业务背景与核心痛点)
Two independent issues require immediate fixes:

1. **ISSUE-1129 — Auditor YOLO Loop**: When the Auditor agent rejects a PRD (`{"status": "REJECTED"}`), `spawn_auditor.py` terminates with `sys.exit(1)`. This triggers an unintended self-healing loop: the Manager LLM is fine-tuned to auto-correct on shell failures, causing it to ignore the mandatory "NO YOLO / Wait for Authorization" prompts and immediately rewrite the PRD without human approval.

2. **Deploy Script Sequence Bug**: In `skills/pm-skill/deploy.sh`, the `gemini skills link` command is placed after the gateway restart logic. When `kit-deploy.sh` sends SIGTERM to trigger gateway restart, the Gemini CLI link step is killed mid-execution. Additionally, `pm-skill/deploy.sh` lacks the `--consent` flag, causing deployments to hang waiting for interactive `[Y/n]` confirmation.

## 2. Requirements & User Stories (需求定义)
1. **Fix Auditor YOLO Loop (ISSUE-1129)**: Modify `spawn_auditor.py` to return `sys.exit(0)` even when the Auditor verdict is `REJECTED`, while still printing a loud warning message so the Manager correctly relays it to the user.
2. **Fix Deploy Script Sequence**: Reorder the steps in `skills/pm-skill/deploy.sh` so that `gemini skills link` executes before gateway restart. Also add `--consent` flag to prevent interactive stalls.

## 3. Architecture & Technical Strategy (架构设计与技术路线)

### Fix 1 — Auditor YOLO Loop (`spawn_auditor.py`):
- After parsing the Auditor JSON verdict, if `status == "REJECTED"`:
  - Print the rejection reason and comments to stdout (loud warning format).
  - Execute `sys.exit(0)` instead of `sys.exit(1)`.
  - If `status == "APPROVED"` or parsing succeeds: also `sys.exit(0)`.
  - Only `sys.exit(1)` on actual subprocess/parsing failures (unrecoverable errors).

### Fix 2 — Deploy Script Sequence (`skills/pm-skill/deploy.sh`):
- Locate the Gemini CLI skill linking step and move it to execute BEFORE the `openclaw gateway restart` block.
- Append `--consent` flag to the `gemini skills link` command to eliminate interactive `[Y/n]` blocking.

## 4. Acceptance Criteria (BDD 黑盒验收标准)

- **Scenario 1:** Auditor REJECTED does not trigger YOLO retry.
  - **Given** `spawn_auditor.py` receives a `{"status": "REJECTED"}` verdict.
  - **When** it processes and outputs the rejection.
  - **Then** the process exits with code `0` and the Manager sees it as a normal output, not a failure.

- **Scenario 2:** Deploy script completes fully without SIGTERM interruption.
  - **Given** a clean system with Gemini CLI available.
  - **When** `./kit-deploy.sh` or `bash skills/pm-skill/deploy.sh` is executed.
  - **Then** the `gemini skills link --consent` step completes successfully before gateway restart, and no `[Y/n]` prompt appears.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Testing**: Add a test in `tests/test_spawn_auditor_rejection.py` that mocks an Auditor REJECTED JSON response and verifies the process exits with code `0`.
- **Integration Testing**: Run `bash skills/pm-skill/deploy.sh` in a sandbox and verify the script completes without hanging on `[Y/n]`.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_auditor.py`
- `skills/pm-skill/deploy.sh`

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

- **For `scripts/spawn_auditor.py` (Auditor rejection handling)**:
```python
# After parsing JSON verdict:
if parsed.get("status") in ("REJECTED", "APPROVED"):
    print(f"\n[Auditor] Status: {parsed.get('status')}")
    if parsed.get('status') == "REJECTED":
        print(f"\n{'='*60}")
        print(f"  AUDITOR REJECTED — Please review the feedback above.")
        print(f"{'='*60}\n")
    sys.exit(0)  # NOT exit(1) — prevents Manager YOLO loop
```

- **For `skills/pm-skill/deploy.sh` (Gemini link before restart)**:
```bash
# Gemini CLI Dual-Compatibility Link — BEFORE gateway restart
if command -v gemini >/dev/null 2>&1; then
    echo "🔗 Gemini CLI detected. Linking skill for dual compatibility..."
    gemini skills link "$PROD_DIR" --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
fi

# Gateway restart — AFTER skill linking
if [ -z "$HOME_MOCK" ] && [ "$NO_RESTART" != "true" ]; then
    openclaw gateway restart || true
fi
```
