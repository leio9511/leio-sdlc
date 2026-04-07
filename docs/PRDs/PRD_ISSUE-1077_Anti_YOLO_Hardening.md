---
Affected_Projects: [leio-sdlc]
---

# PRD: ISSUE-1077 Anti-YOLO Guardrail Hardening

## 1. Context & Problem (业务背景与核心痛点)
The SDLC process is vulnerable to "YOLO" loops where the Main Agent auto-corrects PRDs without human authorization. This is caused by a lack of technical enforcement mechanisms for halting and a failure to mandate explicit string content, allowing LLM hallucination.

## 2. Requirements & User Stories (需求定义)
1.  **Auditor Observability & Interruption**: `spawn_auditor.py` must be upgraded with Slack notifications and a JIT prompt injection mechanism.
2.  **Hardcoded Content Mandate**: A new section must be added to the PRD template to enforce pixel-perfect copying of string literals.
3.  **PM Skill Guardrail**: The `pm-skill/SKILL.md` must be updated with an explicit circuit-breaker instruction.

## 3. Architecture & Technical Strategy (架构设计与技术路线)
-   **`scripts/spawn_auditor.py`**: Add `--channel` support, a fail-fast handshake, and `[ACTION REQUIRED FOR MANAGER]` JIT prompt printing.
-   **`skills/pm-skill/TEMPLATES/PRD.md.template`**: Add a `## 7. HARDCODED CONTENT (CODER MUST COPY EXACTLY)` section.
-   **`skills/pm-skill/SKILL.md`**: Append the `End of Task & Circuit Breaker` guardrail section.
-   **Deployment Strategy**: Changes made to `skills/pm-skill/SKILL.md` within the workspace source will be synchronized to the global runtime skill directory post-merge via the `kit-deploy.sh` pipeline, mitigating any path isolation risks.

## 4. Acceptance Criteria (BDD 黑盒验收标准)
-   **Scenario 1: Auditor Reject Flow with JIT**
    -   **Given** `spawn_auditor.py` is run with a valid `--channel` and the auditor rejects the PRD
    -   **Then** Slack receives status updates and `stdout` ends with the REJECT JIT prompt.
-   **Scenario 2: Auditor Approve Flow with JIT**
    -   **Given** `spawn_auditor.py` is run with a valid `--channel` and the auditor approves the PRD
    -   **Then** Slack receives status updates and `stdout` ends with the APPROVE JIT prompt.
-   **Scenario 3: Handshake Fail**
    -   **Given** `spawn_auditor.py` is run but the channel handshake fails or is missing
    -   **Then** The script terminates immediately (fail-fast) and prints the Handshake Fail JIT prompt.
-   **Scenario 4: Template and Skill Updates**
    -   **Given** The SDLC pipeline completes
    -   **Then** `skills/pm-skill/TEMPLATES/PRD.md.template` contains the exact Hardcoded Content block for PRDs.
    -   **And** `skills/pm-skill/SKILL.md` contains the exact Circuit Breaker block.

## 5. Overall Test Strategy & Quality Goal (测试策略与质量目标)
-   A minimal unit test will verify `spawn_auditor.py` prints the correct JIT prompt.

## 6. Framework Modifications (框架防篡改声明)
> **[CRITICAL GUARDRAIL FOR CODER]**: The file paths listed below are relative to the current project's working directory (`/root/.openclaw/workspace/projects/leio-sdlc`). When using OpenClaw native file tools (`read`, `write`, `edit`), you **MUST use their absolute paths** (e.g., `/root/.openclaw/workspace/projects/leio-sdlc/skills/pm-skill/SKILL.md`) because native tools resolve relative paths against the global OpenClaw root, not the `cwd`.
-   `scripts/spawn_auditor.py`
-   `skills/pm-skill/SKILL.md`
-   `skills/pm-skill/TEMPLATES/PRD.md.template`
-   `tests/test_spawn_auditor.py` (New file)

---
## 7. HARDCODED CONTENT (CODER MUST COPY EXACTLY)

**1. Content for `skills/pm-skill/TEMPLATES/PRD.md.template`:**
(Append the following section to the end of the file)
```markdown
---

## 7. HARDCODED CONTENT (CODER MUST COPY EXACTLY)
> [CRITICAL INSTRUCTION TO CODER] For any modifications involving specific string literals (e.g., SKILL.md content, Playbook rules, JIT prompts, error messages), you MUST NOT generate them yourself. You are required to copy the exact content provided below in this section.
```

**2. Content for `skills/pm-skill/SKILL.md`:**
(Append the following section to the end of the file)
```markdown
## End of Task & Circuit Breaker (CRITICAL)
Once you have written and saved the PRD file, your active role as PM is **100% COMPLETE**.
1. **Trigger Auditor**: You must immediately call `spawn_auditor.py` to check your work.
2. **Circuit Breaker (NO YOLO)**: If the Auditor returns `{"status": "REJECTED"}`, Report the rejection reasons to the Boss, then you MUST immediately halt all further operations and WAIT for explicit instructions. DO NOT ATTEMPT TO AUTO-CORRECT.
3. **Wait for Launch**: If the Auditor returns `{"status": "APPROVED"}`, Notify the Boss of the successful audit, then you MUST immediately halt all further operations and WAIT for explicit authorization to execute.
```

**3. Content for JIT Prompts in `scripts/spawn_auditor.py`:**
- **On Handshake Fail**: `[ACTION REQUIRED FOR MANAGER] [FATAL] Channel handshake failed. You MUST provide a valid --channel parameter (e.g., slack:#XXXX) and retry.`
- **On REJECT**: `[ACTION REQUIRED FOR MANAGER] The Auditor REJECTED the PRD. Report the rejection reasons to the Boss, then you MUST immediately halt all further operations and WAIT for explicit instructions.`
- **On APPROVE**: `[ACTION REQUIRED FOR MANAGER] The Auditor APPROVED the PRD. Notify the Boss of the successful audit, then you MUST immediately halt all further operations and WAIT for explicit authorization to deploy.`
