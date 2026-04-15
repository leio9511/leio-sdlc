---
Affected_Projects: [leio-sdlc]
---

# PRD: Fix_Auditor_YOLO_And_Deploy_Script_Sequence

## 1. Context & Problem (业务背景与核心痛点)
1. **Auditor YOLO Loop**: Currently, when the Auditor rejects a PRD, `spawn_auditor.py` exits with `exit(1)`. This triggers the LLM's trained "self-healing" instinct to fix the shell error, causing it to ignore "NO YOLO" prompts and rewrite the PRD without human approval.
2. **Deploy Script Interruption**: In `pm-skill/deploy.sh`, `gemini skills link` runs after the gateway restart, leading to SIGTERM killing the link process. It also lacks `--consent`.

## 2. Requirements & User Stories (需求定义)
1. **Suppress YOLO Reflex**: Modify `spawn_auditor.py` to return `exit(0)` on `REJECTED` verdicts.
2. **Fix Deploy Flow**: Reorder `pm-skill/deploy.sh` to link skills before restart and add `--consent`.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
- **Boss Mandate (Strategic Override)**: This design intentionally deviates from standard Unix "Semantic Exit Code" patterns to address the unique behavioral quirk of LLM Agents. **Boss Mandate**: "This is the only viable short-term fix to break the illusion of LLM. Boss will not treat 'Reject from Auditor' as Error, it is information for Boss to take into consideration. Boss can override the rejection and decide to move on. So it should be treated as exit 0."
- **Exit Code Logic**: `spawn_auditor.py` will exit with `0` for both `APPROVED` and `REJECTED`. It will only exit with `1` on catastrophic process failures (e.g., Python crash, JSON corrupted beyond repair).

## 4. Acceptance Criteria (BDD 黑盒验收标准)
- **Scenario 1**: Auditor REJECTED does not trigger Manager auto-fix.
  - **Given** Auditor returns `{"status": "REJECTED"}`.
  - **Then** `spawn_auditor.py` exits with code `0`.
- **Scenario 2**: Deploy script completes fully.
  - **Given** Gemini CLI is available.
  - **Then** `gemini skills link` completes before restart.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
- **Unit Test**: Mock Auditor rejection and assert `exit(0)`.

## 6. Framework Modifications (框架防篡改声明)
- `scripts/spawn_auditor.py`
- `skills/pm-skill/deploy.sh`

## 7. Hardcoded Content (硬编码内容)

### Exact Text Replacements:

- **For `scripts/spawn_auditor.py` (Final Verdict Handling)**:
```python
    if status == "APPROVED":
        agent_driver.notify_channel(args.channel, "Auditor APPROVED the PRD.", "auditor_approved", {"prd_file": args.prd_file})
        print("[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD. Notify the Boss of the successful audit, then you MUST immediately halt all further operations and WAIT for explicit authorization to deploy.")
        sys.exit(0)
    else:
        agent_driver.notify_channel(args.channel, "Auditor REJECTED the PRD.", "auditor_rejected", {"prd_file": args.prd_file})
        print("[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD. Report the rejection reasons to the Boss, then you MUST immediately halt all further operations and WAIT for explicit instructions.")
        sys.exit(0) # Boss Mandate: Prevent LLM YOLO retry by returning success code
```

- **For `skills/pm-skill/deploy.sh` (Link before restart)**:
```bash
if command -v gemini >/dev/null 2>&1; then
    echo "🔗 Gemini CLI detected. Linking skill for dual compatibility..."
    gemini skills link "$PROD_DIR" --consent || echo "⚠️ Gemini link failed, but deployment succeeded."
fi

if [ -z "$HOME_MOCK" ] && [ "$NO_RESTART" != "true" ]; then
    openclaw gateway restart || true
fi
```
