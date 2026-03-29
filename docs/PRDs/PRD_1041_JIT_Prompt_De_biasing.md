---
Affected_Projects: [leio-sdlc]
---
# PRD-1041: Review and fix JIT prompts to remove LLM attention bias

## 1. Context & Motivation
The current JIT error messages, specifically the workspace isolation error in `orchestrator.py`, contain suggestive phrasing like 'you must explicitly add the parameter: --enable-exec-from-workspace'. This misdirects the LLM's attention, causing it to blindly append the parameter and bypass security rather than investigating why it is running in the workspace.

## 2. Requirements
1. **Audit and Refactor**: Review and refactor all JIT error messages in the SDLC framework (`orchestrator.py`) related to fatal guardrails.
2. **Strong Block + Weak Disclaimer Pattern**: The new error structure MUST use this pattern.
   - *Example*: "[FATAL] DO NOT RUN FROM WORKSPACE! You MUST execute the SDLC engine from the safe runtime sandbox: `~/.openclaw/skills/leio-sdlc/scripts/orchestrator.py` (Only if you are actively developing the SDLC engine itself and accept the risks of branch pollution, you may force an override with `--enable-exec-from-workspace`.)".
3. **Framework Modifications**: Apply these changes to `scripts/orchestrator.py`.

## 3. Technical Implementation
- Locate the `scripts/orchestrator.py` script.
- Identify the workspace isolation check and any other fatal guardrail error messages.
- Rewrite the `print` or `logging` statements to match the required 'Strong Block + Weak Disclaimer' pattern.
- Ensure the primary directive (how to fix it correctly by running from the sandbox) is prominent, and the override is minimized/parenthetical.

## 4. Acceptance Criteria
- JIT error for workspace execution uses the exact 'Strong Block + Weak Disclaimer' pattern.
- The prompt explicitly warns against running from the workspace and points to the safe sandbox path.
- The override parameter is framed as a risk-accepting disclaimer.
